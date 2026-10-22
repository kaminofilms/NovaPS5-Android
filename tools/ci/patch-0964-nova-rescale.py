#!/usr/bin/env python3
"""Independent Nova surface scaler; apply after all 0.9.63 overlays.

CapyPS5 v0.0.1 was studied as an architectural reference; its implementation
is not incorporated. Unsupported consumers permanently promote an image to
native size. Compute dispatches are deliberately unchanged.
"""
from pathlib import Path
import sys

ROOT = Path(sys.argv[1])
REPO = Path(__file__).resolve().parents[2]
changes = {}


def edit(name, before, after, count=1):
    p = ROOT / 'src' / name
    s = changes.get(p, p.read_text())
    if s.count(before) != count:
        raise SystemExit(f'NOVA_RESCALE: anchor changed: {name}: {before[:70]!r} ({s.count(before)})')
    changes[p] = s.replace(before, after)


def include(name, header):
    p = ROOT / 'src' / name
    s = changes.get(p, p.read_text())
    if f'#include "{header}"' not in s:
        changes[p] = f'#include "{header}"\n' + s


im = 'graphics/host_gpu/renderer/image/image.cpp'
ih = 'graphics/host_gpu/renderer/image/image.h'
tc = 'graphics/host_gpu/renderer/cache/textureCache.cpp'
th = 'graphics/host_gpu/renderer/cache/textureCache.h'
rd = 'graphics/host_gpu/renderer/renderDraw.cpp'
ph = 'graphics/host_gpu/renderer/pipeline/pipelineCache.h'
pc = 'graphics/host_gpu/renderer/pipeline/pipelineCache.cpp'
sh = 'graphics/host_gpu/renderer/pipeline/shaders.cpp'
cx = 'graphics/host_gpu/renderer/context.cpp'

for f in [ih, th, ph]:
    include(f, 'common/novaRescale.h')

# ImageInfo remains in guest coordinates; only VulkanImage is allocated smaller.
edit(ih, 'Image(GraphicContext& graphics, CommandScheduler& scheduler, const ImageInfo& info);',
     'Image(GraphicContext& graphics, CommandScheduler& scheduler, const ImageInfo& info, uint32_t nova_permille = 1000);')
edit(ih, '\tVulkanImage      backing;', '''	VulkanImage      backing;
	uint32_t nova_permille = 1000;
	bool NovaScaled() const { return nova_permille < 1000; }
	void NovaNative(const char* reason);
	vk::ImageCreateInfo nova_create_info {};
''')
edit(im, 'Image::Image(GraphicContext& graphics, CommandScheduler& scheduler, const ImageInfo& image_info)',
     'Image::Image(GraphicContext& graphics, CommandScheduler& scheduler, const ImageInfo& image_info, uint32_t nova_requested)')
edit(im, '\tcreate.extent        = info.extent;', '''	create.extent        = info.extent;
	nova_permille = nova_requested;
	if (NovaScaled()) {
		create.extent.width = NovaRescale::Dimension(info.extent.width, nova_permille);
		create.extent.height = NovaRescale::Dimension(info.extent.height, nova_permille);
	}
''')
edit(im, '\tif (!graphics.CreateImage(create, backing)) {', '''	nova_create_info = create;
	nova_create_info.pNext = nullptr;
	if (!graphics.CreateImage(create, backing)) {''')

# Promotions happen before native-size buffer copies, image copies or resolves.
# Retire old views/backings at the scheduler tick, rather than destroying objects
# still referenced by previously submitted command buffers.
promotion = r'''
void Image::NovaNative(const char* reason) {
	if (!NovaScaled()) return;
	m_scheduler.EndRendering();
	auto create = nova_create_info;
	create.extent = info.extent;
	VulkanImage replacement {};
	if (!m_graphics.CreateImage(create, replacement)) EXIT("NOVA_RESCALE: native promotion allocation failed\n");
	auto command = m_scheduler.Current().Handle();
	Transit(vk::ImageLayout::eTransferSrcOptimal, vk::AccessFlagBits2::eTransferRead, {}, command);
	vk::ImageMemoryBarrier2 barrier {};
	barrier.dstStageMask = vk::PipelineStageFlagBits2::eAllTransfer;
	barrier.dstAccessMask = vk::AccessFlagBits2::eTransferWrite;
	barrier.oldLayout = vk::ImageLayout::eUndefined;
	barrier.newLayout = vk::ImageLayout::eTransferDstOptimal;
	barrier.srcQueueFamilyIndex = barrier.dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
	barrier.image = replacement.image;
	barrier.subresourceRange = {FullAspectMask(backing.format),0,1,0,1};
	vk::DependencyInfo dependency {};
	dependency.imageMemoryBarrierCount = 1;
	dependency.pImageMemoryBarriers = &barrier;
	command.pipelineBarrier2(dependency);
	// Vulkan requires one aspect per depth/stencil blit and nearest filtering.
	const auto aspects = FullAspectMask(backing.format);
	for (auto aspect : {vk::ImageAspectFlagBits::eColor, vk::ImageAspectFlagBits::eDepth,
	                   vk::ImageAspectFlagBits::eStencil}) {
		if (!(aspects & aspect)) continue;
		vk::ImageBlit region {};
		region.srcSubresource = {aspect,0,0,1};
		region.dstSubresource = {aspect,0,0,1};
		region.srcOffsets[1] = vk::Offset3D{int32_t(backing.extent.width),int32_t(backing.extent.height),1};
		region.dstOffsets[1] = vk::Offset3D{int32_t(info.extent.width),int32_t(info.extent.height),1};
		command.blitImage(backing.image,vk::ImageLayout::eTransferSrcOptimal,
		                  replacement.image,vk::ImageLayout::eTransferDstOptimal,
		                  1,&region,vk::Filter::eNearest);
	}
	replacement.state = {vk::PipelineStageFlagBits2::eAllTransfer,
	                     vk::AccessFlagBits2::eTransferWrite,vk::ImageLayout::eTransferDstOptimal};
	auto previous = std::make_shared<VulkanImage>();
	auto swap_image=[](VulkanImage& a,VulkanImage& b) {
		using std::swap;
		swap(a.format,b.format);swap(a.image_type,b.image_type);swap(a.extent,b.extent);
		swap(a.layers,b.layers);swap(a.mip_levels,b.mip_levels);swap(a.samples,b.samples);
		swap(a.usage,b.usage);swap(a.flags,b.flags);swap(a.image,b.image);
		swap(a.state,b.state);swap(a.subresource_states,b.subresource_states);swap(a.allocation,b.allocation);
	};
	swap_image(*previous,backing);
	auto previous_views = std::move(views);
	views.clear();
	swap_image(backing,replacement);
	nova_permille = 1000;
	auto* graphics = &m_graphics;
	m_scheduler.DeferOperation([graphics,previous,previous_views=std::move(previous_views)]() mutable {
		for (const auto& v : previous_views) if(v.view) graphics->device.destroyImageView(v.view,nullptr);
		graphics->DeleteImage(*previous);
	});
	NovaRescale::Note(false, reason);
}

'''
edit(im, 'Image::~Image() {', promotion + 'Image::~Image() {')
edit(im, '''void Image::Upload(std::span<const vk::BufferImageCopy> copies, vk::Buffer buffer, uint64_t offset,
                   uint64_t size) {''', '''void Image::Upload(std::span<const vk::BufferImageCopy> copies, vk::Buffer buffer, uint64_t offset,
                   uint64_t size) {
	NovaNative("upload");''')
edit(im, '''void Image::Download(std::span<const vk::BufferImageCopy> copies, vk::Buffer buffer,
                     uint64_t offset, uint64_t size) {''', '''void Image::Download(std::span<const vk::BufferImageCopy> copies, vk::Buffer buffer,
                     uint64_t offset, uint64_t size) {
	NovaNative("readback");''')
edit(im, 'void Image::CopyImage(Image& source) {', 'void Image::CopyImage(Image& source) {\n\tNovaNative("copy-destination"); source.NovaNative("copy-source");')
edit(im, 'void Image::CopyImageWithBuffer(Image& source, Buffer& buffer, TileManager& tiler) {',
     'void Image::CopyImageWithBuffer(Image& source, Buffer& buffer, TileManager& tiler) {\n\tNovaNative("buffer-copy"); source.NovaNative("buffer-copy-source");')
edit(im, 'void Image::CopyMip(Image& source, uint32_t mip, uint32_t layer) {',
     'void Image::CopyMip(Image& source, uint32_t mip, uint32_t layer) {\n\tNovaNative("mip-copy"); source.NovaNative("mip-copy-source");')
edit(im, '''                    const ImageSubresourceRange& destination_range) {''', '''                    const ImageSubresourceRange& destination_range) {
	NovaNative("resolve"); source.NovaNative("resolve-source");''')

# Decide scale at creation, with format capability checks for every eventual
# fallback. Mere Vulkan STORAGE usage capability does not mean a guest storage use.
edit(th, 'ImageId     InsertImage(const ImageInfo& info);', 'ImageId     InsertImage(const ImageInfo& info, uint32_t nova_permille = 1000);')
edit(tc, 'ImageId TextureCache::InsertImage(const ImageInfo& info) {\n\tconst auto id = m_slot_images.insert(m_graphics, m_scheduler, info);',
     'ImageId TextureCache::InsertImage(const ImageInfo& info, uint32_t nova_permille) {\n\tconst auto id = m_slot_images.insert(m_graphics, m_scheduler, info, nova_permille);')
edit(tc, '\t\t\tresult         = InsertImage(desc.info);', '''			uint32_t nova_permille = 1000;
			const auto& ni = desc.info;
			const bool target = desc.type == BindingType::RenderTarget || desc.type == BindingType::DepthTarget || desc.type == BindingType::VideoOut;
			const NovaRescale::Candidate candidate {ni.extent.width,ni.extent.height,ni.extent.depth,
			    ni.resources.layers,ni.resources.levels,ni.samples,target,ni.IsBlock(),false,false};
			const auto features = m_graphics.GetFormatProperties(ni.pixel_format).optimalTilingFeatures;
			const auto required = vk::FormatFeatureFlagBits::eBlitSrc | vk::FormatFeatureFlagBits::eBlitDst;
			if (ni.type == Prospero::ImageType::kColor2D && NovaRescale::Eligible(candidate,NovaRescale::Permille()) &&
			    (features & required) == required) {
				nova_permille = NovaRescale::Permille();
				NovaRescale::Note(true,"allocation");
			}
			result = InsertImage(desc.info,nova_permille);''')
edit(tc, '\tMaterializeColorClear(result, desc, metadata_base_layer);', '''	if (desc.type == BindingType::Storage) m_slot_images[result].NovaNative("storage");
	MaterializeColorClear(result, desc, metadata_base_layer);''')
edit(tc, 'std::max(image.info.extent.width >> range.baseMipLevel, 1u),\n\t\t    std::max(image.info.extent.height >> range.baseMipLevel, 1u)',
     'std::max(image.backing.extent.width >> range.baseMipLevel, 1u),\n\t\t    std::max(image.backing.extent.height >> range.baseMipLevel, 1u)')

# Reuse Nova's existing guest-space FragCoord bridge, without its per-pass proxies.
rs = 'common/novaRasterScale.h'
include(rs, 'common/novaRescale.h')
edit(rs, 'inline bool Enabled(){return ScalePct()<100;}',
     'inline bool Enabled(){return NovaRescale::Enabled() || ScalePct()<100;}')
edit(rs, ' if(!Enabled()||h<540||uint64_t(w)*9!=uint64_t(h)*16)return {};',
     ' if(NovaRescale::Enabled()||!Enabled()||h<540||uint64_t(w)*9!=uint64_t(h)*16)return {};')
edit('graphics/host_gpu/renderer/renderTarget.h', 'struct RenderState {',
     'struct RenderState {\n\tbool nova_backing_scaled = false;\n\tfloat nova_scale_x = 1.f, nova_scale_y = 1.f;')
edit(cx, 'state.raster_width && attachment.raster_owner', 'state.raster_width && !state.nova_backing_scaled && attachment.raster_owner')
edit(cx, 'state.raster_width && depth_stencil.raster_owner', 'state.raster_width && !state.nova_backing_scaled && depth_stencil.raster_owner')
edit(cx, 'if(m_render_state.raster_width){', 'if(m_render_state.raster_width && !m_render_state.nova_backing_scaled){')

# Unsupported descriptor paths switch back to a native allocation before final
# view acquisition. This keeps compute grids, bindless arrays, mips and stores
# exact while the initial scaler covers ordinary raster/sampled 2D targets.
ds = 'graphics/host_gpu/renderer/pipeline/descriptors.cpp'
edit(ds, '\t\tauto binding = ResolveTexture(program.info.images[i], snapshot.images[i]);', '''		auto binding = ResolveTexture(program.info.images[i], snapshot.images[i]);
		if (binding.image_id && NovaRescale::Enabled()) {
			const auto& resource = program.info.images[i];
			if (program.stage == ShaderType::Compute || i >= NovaRescale::MaxBindings ||
			    resource.indirect_root != ShaderRecompiler::IR::ImageResource::NoIndirectImage ||
			    resource.mip_mode == ShaderRecompiler::IR::ImageMipMode::Dynamic ||
			    binding.desc.type == TextureCache::BindingType::Storage)
				m_context.GetTextureCache().GetImage(binding.image_id).NovaNative("descriptor-fallback");
		}''')

# Passes with different scaling ratios or shader side effects use native
# attachments. Normalize before final descriptors are acquired, then refresh views.
edit(rd, '\tPrepareGraphicsBindings(stages, std::span {state.color_info, state.color_count});', '''	if (NovaRescale::Enabled()) {
		auto& cache = m_context.GetTextureCache();
		std::array<Image*,RENDER_COLOR_ATTACHMENTS_MAX+1> targets {};
		uint32_t count = 0;
		for (uint32_t i=0;i<state.color_count;i++) if(state.color_info[i].image_id)
			targets[count++] = &cache.GetImage(state.color_info[i].image_id);
		if(state.depth_info.image_id) targets[count++] = &cache.GetImage(state.depth_info.image_id);
		bool native = false;
		for (const auto* stage : stages) {
			if(stage->runtime->program->has_address_writes || HasShaderBufferWrites(*stage->runtime)) native=true;
			for(const auto& r:stage->runtime->program->info.images) if(r.written) native=true;
		}
		for(uint32_t i=1;i<count;i++) {
			const auto& a=*targets[0]; const auto& b=*targets[i];
			if(!NovaRescale::Compatible(a.backing.extent.width,a.backing.extent.height,a.info.extent.width,a.info.extent.height,
			                            b.backing.extent.width,b.backing.extent.height,b.info.extent.width,b.info.extent.height)) native=true;
		}
		if(native) for(uint32_t i=0;i<count;i++) targets[i]->NovaNative("mixed-pass-or-side-effect");
	}
	PrepareGraphicsBindings(stages, std::span {state.color_info, state.color_count});''')

# Native copy-depth-to-colour bypasses the ordinary shader path.
edit(rd, '\tif (CopyDepthToColor(buffer, draw, emit, state)) {', '''	if (NovaRescale::Enabled() && buffer.GetRegisters().GetRenderControl().copy_depth_to_color) {
		auto& cache=m_context.GetTextureCache();
		if(state.depth_info.image_id) cache.GetImage(state.depth_info.image_id).NovaNative("depth-color-copy");
		for(uint32_t i=0;i<state.color_count;i++) if(state.color_info[i].image_id)
			cache.GetImage(state.color_info[i].image_id).NovaNative("depth-color-copy");
	}
	if (CopyDepthToColor(buffer, draw, emit, state)) {''')

# Finish attachment uploads before choosing a pass ratio or collecting views.
# An upload may promote just one attachment to native; all the others must then
# be promoted before any view is returned to the caller.
edit(rd, '\tauto&       cache = m_context.GetTextureCache();\n\tRenderState state {};', '''	 auto& cache = m_context.GetTextureCache();
	if(NovaRescale::Enabled()) {
		std::array<Image*,RENDER_COLOR_ATTACHMENTS_MAX+1> owners {};
		uint32_t count=0;
		for(uint32_t i=0;i<color_count;i++) {
			(void)cache.FindRenderTarget(colors[i].image_id,colors[i].desc);
			owners[count++]=&cache.GetImage(colors[i].image_id);
		}
		if(depth.image_id) {
			(void)cache.FindDepthTarget(depth.image_id,depth.desc);
			owners[count++]=&cache.GetImage(depth.image_id);
		}
		bool mismatch=false;
		for(uint32_t i=1;i<count;i++) {
			const auto& a=*owners[0]; const auto& b=*owners[i];
			if(!NovaRescale::Compatible(a.backing.extent.width,a.backing.extent.height,a.info.extent.width,a.info.extent.height,
			                           b.backing.extent.width,b.backing.extent.height,b.info.extent.width,b.info.extent.height)) mismatch=true;
		}
		if(mismatch) for(uint32_t i=0;i<count;i++) owners[i]->NovaNative("attachment-refresh-mismatch");
	}
	RenderState state {};''')

# Acquisition can perform an upload (which promotes a target). Match the final
# attachment allocations; use guest dimensions for viewport/scissor conversion.
edit(rd, '\treturn state;\n}\n\nstatic uint32_t DrawColorOutputMask', '''	if(NovaRescale::Enabled()) {
		const Image* first=nullptr;
		for(const auto& a:state.color_attachments) if(a.image_view && a.raster_owner) {first=a.raster_owner;break;}
		if(!first) first=state.depth_stencil_attachment.raster_owner;
		if(first && first->NovaScaled()) {
			state.nova_backing_scaled=true;
			state.nova_scale_x=float(first->backing.extent.width)/first->info.extent.width;
			state.nova_scale_y=float(first->backing.extent.height)/first->info.extent.height;
			state.raster_width=uint32_t((uint64_t(state.width)*first->backing.extent.width+first->info.extent.width-1)/first->info.extent.width);
			state.raster_height=uint32_t((uint64_t(state.height)*first->backing.extent.height+first->info.extent.height-1)/first->info.extent.height);
		}
	}
	return state;
}

static uint32_t DrawColorOutputMask''')
edit(rd, 'const float sx=float(rendering.raster_width)/rendering.width, sy=float(rendering.raster_height)/rendering.height;',
     'const float sx=rendering.nova_backing_scaled?rendering.nova_scale_x:float(rendering.raster_width)/rendering.width, sy=rendering.nova_backing_scaled?rendering.nova_scale_y:float(rendering.raster_height)/rendering.height;')
edit(rd, 'rendering.raster_width?float(rendering.width)/rendering.raster_width:1.f',
     'rendering.nova_backing_scaled?1.f/rendering.nova_scale_x:(rendering.raster_width?float(rendering.width)/rendering.raster_width:1.f)')
edit(rd, 'rendering.raster_height?float(rendering.height)/rendering.raster_height:1.f',
     'rendering.nova_backing_scaled?1.f/rendering.nova_scale_y:(rendering.raster_height?float(rendering.height)/rendering.raster_height:1.f)')

# Keep the specialization payload in PipelineStaticParameters so both its hash
# and exact equality, including background compilation jobs, include the scales.
edit(ph, '\tbool operator==(const PipelineStaticParameters& other) const noexcept;', '''	NovaRescale::PipelineData nova_rescale {};
	bool operator==(const PipelineStaticParameters& other) const noexcept;''')
edit(ph, 'static_assert(sizeof(PipelineStaticParameters) == 116);',
     'static_assert(sizeof(PipelineStaticParameters) == 116 + sizeof(NovaRescale::PipelineData));')
edit(pc, '\tauto& static_params         = key.static_params;', '''	auto& static_params         = key.static_params;
	static_params.nova_rescale = NovaRescale::Pending();''')
edit(pc, 'disk_directory(NovaShaderDisk::Directory(signature, PipelineCacheTitleId()))',
     'disk_directory(NovaShaderDisk::Directory(signature + (NovaRescale::Enabled()?":rescale64":":native64"), PipelineCacheTitleId()))')

# Acquire target views before pipeline lookup, then snapshot binding dimensions.
# No scheduler operations are permitted after the final snapshot/lookup phase.
p = ROOT/'src'/rd
s = changes[p]
start = s.index('\tauto* nova_pipeline = m_context.GetPipelineCache().GetGraphicsPipeline(')
end = s.index('\n\tvk::ImageAspectFlags feedback_aspects;',start)
lookup = s[start:end]
s = s[:start]+s[end:]
anchor = '\n\t// Resource preparation above may synchronously finish and restart the scheduler.'
if s.count(anchor)!=1: raise SystemExit('NOVA_RESCALE: final-draw anchor changed')
snapshot = '''
	NovaRescale::Pending() = {};
	if(NovaRescale::Enabled()) {
		// Reacquire every sampled view after possible native promotions in target acquisition.
		for(auto* stage:stages) RebindImages(*stage);
		for(uint32_t si=0;si<stages.size();si++) {
			const auto* stage=stages[si];
			const uint32_t slot=stage->runtime->program->stage==ShaderType::Pixel?3u:si;
			if(slot>=4) continue;
			for(uint32_t i=0;i<stage->images.size() && i<NovaRescale::MaxBindings;i++) {
				const auto& b=stage->images[i]; if(!b.image_id) continue;
				const auto& image=m_context.GetTextureCache().GetImage(b.image_id);
				if(!image.NovaScaled()) continue;
				auto* data=NovaRescale::Pending().stages[slot]+i*4;
				data[0]=image.info.extent.width; data[1]=image.info.extent.height;
				data[2]=image.backing.extent.width; data[3]=image.backing.extent.height;
			}
		}
	}
'''
changes[p]=s.replace(anchor,'\n'+snapshot+lookup+'\n'+anchor,1)

# Each shader stage gets its own immutable per-binding metadata. IDs 400..527
# are reserved for this schema, independently of the existing push-constant ABI.
# Specialization avoids expanding the already full 128-byte guest push block.
spec = '''
	std::array<std::array<vk::SpecializationMapEntry,NovaRescale::StageWords>,4> nova_entries {};
	std::array<vk::SpecializationInfo,4> nova_specs {};
	if(NovaRescale::Enabled()) {
		for(uint32_t slot=0;slot<4;slot++) {
			for(uint32_t word=0;word<NovaRescale::StageWords;word++)
				nova_entries[slot][word]=vk::SpecializationMapEntry{NovaRescale::SpecBase+word,word*uint32_t(sizeof(uint32_t)),sizeof(uint32_t)};
			nova_specs[slot].mapEntryCount=NovaRescale::StageWords;
			nova_specs[slot].pMapEntries=nova_entries[slot].data();
			nova_specs[slot].dataSize=sizeof(NovaRescale::StageData);
			nova_specs[slot].pData=static_params.nova_rescale.stages[slot];
		}
		for(uint32_t i=0;i<shader_stage_count;i++) {
			const uint32_t slot=shader_stages[i].stage==vk::ShaderStageFlagBits::eFragment?3u:i;
			if(slot<4) shader_stages[i].pSpecializationInfo=&nova_specs[slot];
		}
	}

'''
edit(sh, '\tvk::VertexInputAttributeDescription input_attr[ShaderVertexInputInfo::RES_MAX] {};',
     spec+'\tvk::VertexInputAttributeDescription input_attr[ShaderVertexInputInfo::RES_MAX] {};')
# Existing GPL sub-library keys do not contain this metadata. Use complete
# pipelines for this opt-in path until the library schema is extended.
edit(sh, 'if (graphics.graphics_pipeline_library_enabled && !rect_list && !tessellation) {',
     'if (graphics.graphics_pipeline_library_enabled && !NovaRescale::Enabled() && !rect_list && !tessellation) {')

# Integer fetch/imageLoad coordinates and size queries use the exact original
# dimensions, not an inverse of a rounded extent. Normalized UVs are unchanged.
ei = 'graphics/shader/recompiler/backend/spirv/spirvEmitterInternal.h'
ec = 'graphics/shader/recompiler/backend/spirv/spirvEmitterImage.cpp'
edit('graphics/shader/recompiler/backend/spirv/SpirvBuilder.h',
     '\tuint32_t DefineGlobalVariable(uint32_t pointer_type, spv::StorageClass storage_class);', '''	// A specialization constant's identity includes its SpecId, even when defaults
	// are equal. Ordinary Constant() interns equal literals and cannot be used here.
	uint32_t NovaSpecializationU32(uint32_t type, uint32_t value, uint32_t spec_id) {
		const auto id = AllocateId();
		AppendInstruction(m_declarations, spv::OpSpecConstant, type, id, value);
		AddAnnotation(spv::OpDecorate,id,spv::DecorationSpecId,spec_id);
		return id;
	}
	uint32_t DefineGlobalVariable(uint32_t pointer_type, spv::StorageClass storage_class);''')
include(ei,'common/novaRescale.h')
edit(ei, '\tBuilder                                          builder;',
     '\tstd::array<uint32_t,NovaRescale::StageWords> nova_rescale_ids {};\n\tBuilder                                          builder;')
helper = r'''
uint32_t NovaImageWord(EmitterState& s, uint32_t binding, uint32_t component) {
	const auto index=binding*4+component;
	auto& id=s.nova_rescale_ids[index];
	if(id==0) {
		id=s.builder.NovaSpecializationU32(TypeU32(s),0u,NovaRescale::SpecBase+index);
	}
	return id;
}
uint32_t NovaImageCoordinate(ValueEmitContext& ctx, const IR::MemoryInfo& mem, uint32_t value, uint32_t axis) {
	if(!NovaRescale::Enabled() || mem.resource>=NovaRescale::MaxBindings) return value;
	auto& s=ctx.state;
	const auto guest=NovaImageWord(s,mem.resource,axis);
	const auto host=NovaImageWord(s,mem.resource,axis+2);
	const auto active=Binary(s,spv::OpINotEqual,TypeBool(s),host,ConstantU32(s,0));
	const auto divisor=Select(s,TypeU32(s),active,guest,ConstantU32(s,1));
	const auto signed_value=Unary(s,spv::OpBitcast,TypeI32(s),value);
	const auto pixels=Unary(s,spv::OpConvertSToF,TypeF32(s),signed_value);
	const auto ratio=Binary(s,spv::OpFDiv,TypeF32(s),
	    Unary(s,spv::OpConvertUToF,TypeF32(s),host),Unary(s,spv::OpConvertUToF,TypeF32(s),divisor));
	const auto scaled=Binary(s,spv::OpFMul,TypeF32(s),pixels,ratio);
	const auto floored=EmitGlsl<GLSLstd450Floor,IR::Type::F32>(s,scaled);
	const auto integer=Unary(s,spv::OpConvertFToS,TypeI32(s),floored);
	return Select(s,TypeU32(s),active,Unary(s,spv::OpBitcast,TypeU32(s),integer),value);
}

'''
edit(ec, 'uint32_t CoordU32(ValueEmitContext& ctx, const IR::MemoryInfo& mem, const IR::Inst& address,',
     helper+'uint32_t CoordU32(ValueEmitContext& ctx, const IR::MemoryInfo& mem, const IR::Inst& address,')
edit(ec, '\tconst auto x          = AddressU32(ctx, mem, address, 0);',
     '\tconst auto x          = NovaImageCoordinate(ctx,mem,AddressU32(ctx,mem,address,0),0);')
edit(ec, 'mem.image_address_components > 1u ? AddressU32(ctx, mem, address, 1)',
     'mem.image_address_components > 1u ? NovaImageCoordinate(ctx,mem,AddressU32(ctx,mem,address,1),1)')
edit(ec, '\tif (info.multisampled == 0u) {\n\t\tresult[3] = ctx.state.builder.AllocateId();', '''	if(NovaRescale::Enabled() && mem.resource<NovaRescale::MaxBindings) {
		auto& s=ctx.state;
		for(uint32_t axis=0;axis<std::min(components,2u);axis++) {
			const auto guest=NovaImageWord(s,mem.resource,axis);
			const auto host=NovaImageWord(s,mem.resource,axis+2);
			const auto active=Binary(s,spv::OpINotEqual,TypeBool(s),host,ConstantU32(s,0));
			result[axis]=Select(s,TypeU32(s),active,guest,result[axis]);
		}
	}
	if (info.multisampled == 0u) {
		result[3] = ctx.state.builder.AllocateId();''')

# A promoted backing can invalidate a view collected earlier in the same
# discovery. Final RebindImages acquisition above refreshes all graphics views.
# Compute views are native before binding and dispatch dimensions stay exact.

# No file is changed until every anchor in this complete overlay has matched.
changes[ROOT / 'src/common/novaRescale.h'] = (REPO / 'native/novarescale/policy.h').read_text()
for p,s in changes.items():
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(s)
print('NOVA_RESCALE: allocation and native-consumer promotion installed')
