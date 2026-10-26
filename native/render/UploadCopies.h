#pragma once
#include <cstdint>
#include <limits>
namespace NovaRender {
// Merge only copies adjacent in both staging and destination memory. Never
// bridge excluded GPU-dirty bytes or change copy order.
template<class Copies>
void AppendUploadCopy(Copies& copies, uint64_t source, uint64_t destination, uint64_t bytes) {
 if (!bytes) return;
 if (!copies.empty()) {
  auto& last=copies.back();
  const auto limit=std::numeric_limits<uint64_t>::max();
  if (last.size<=limit-last.srcOffset && last.size<=limit-last.dstOffset &&
      last.srcOffset+last.size==source && last.dstOffset+last.size==destination &&
      bytes<=limit-last.size) {last.size+=bytes;return;}
 }
 copies.emplace_back(source,destination,bytes);
}
}
