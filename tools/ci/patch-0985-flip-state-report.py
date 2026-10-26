#!/usr/bin/env python3
"""Expose actual flip state/group without changing completion or retirement."""
from pathlib import Path
import sys
p=Path(sys.argv[1])/'src/graphics/presentation/videoOut.cpp';s=p.read_text()
old='''				std::fprintf(stderr, "NOVA_VIDEO:   request %llu index=%d state=%d source=%d pending=%d gcq=%d\\n",
				             static_cast<unsigned long long>(r.id), r.index, static_cast<int>(r.state), static_cast<int>(r.source),
				             r.cfg != nullptr ? static_cast<int>(r.cfg->flip_status.flipPendingNum) : -1,
				             r.cfg != nullptr ? static_cast<int>(r.cfg->flip_status.gcQueueNum) : -1);'''
new='''				// State 2 is Ready (completion callback already published), not Recording.
				constexpr const char* names[]={"Reserved","Recording","Ready","Presenting"};
				static_assert(static_cast<unsigned>(RequestState::Presenting)==3);
				const auto state=static_cast<unsigned>(r.state);
				std::fprintf(stderr, "NOVA_VIDEO:   request %llu index=%d state=%d state_name=%s source=%d pending=%d gcq=%d group=%llu owner=%d generation=%llu prepared=%d\\n",
				             static_cast<unsigned long long>(r.id), r.index, static_cast<int>(r.state),state<4?names[state]:"Invalid",static_cast<int>(r.source),
				             r.cfg != nullptr ? static_cast<int>(r.cfg->flip_status.flipPendingNum) : -1,
				             r.cfg != nullptr ? static_cast<int>(r.cfg->flip_status.gcQueueNum) : -1,
				             static_cast<unsigned long long>(r.group),r.group==r.id,
				             static_cast<unsigned long long>(r.generation),r.frame!=nullptr);'''
if s.count(old)!=1:raise SystemExit('0985 changed report anchor; no source written')
p.write_text(s.replace(old,new,1));print('0985: freeze dump names actual flip states/group; completion semantics unchanged')
