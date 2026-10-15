# Nova PS5 0.9.19: default subgroup size correction

The 0.9.18 device test still rejected 192 mesh invocations. It did not prove
that the wave64 packing path activated. That release's selector mistakenly
required the advertised default subgroup size to equal 64.

The pinned Turnip source computes subgroupSize as threadsize_base multiplied
by two when expose_double_threadsize is set. The A8xx half-wave patch separately
exposes a minimum subgroup size of 32. Therefore a default size of 128 must not
exclude an explicitly requested, supported mesh subgroup size of 32.

0.9.19 accepts native defaults of at least 64 for the existing wave64 packing
path, while retaining every feature, stage, subgroup-range and output limit
check. Tests now cover native defaults of both 64 and 128, including all guest
lanes for 192/256-invocation workgroups and rejection without the required
feature or fitting limit. No workgroup or geometry output is truncated.

This corrects a verified source bug. The provided device log does not contain
the default subgroup, mesh wave size or feature gate, so it does not establish
which condition prevented packing on that device. A remaining fatal now reports
all of those values plus both requested and supported limits, in bytes for LDS.
The wave32 guest case remains guarded; this release does not claim a general
fallback for guest wave32 workgroups that exceed the driver's mesh limits.

The driver remains the checksum-pinned Turnip 20261012 A8xx bundle. Physical
device rendering remains unverified until the next test.
