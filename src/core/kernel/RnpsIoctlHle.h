#pragma once
#include <cstddef>
#include <cstdint>
#include <functional>
#include <span>
#include <utility>

namespace Nova::Dashboard {
inline constexpr uint32_t VerifyDecryptRnpsBundle = 0xc0105203;
// Observed 64-bit in-place request in zecoxao/decrypt_rnps. No output pointer field.
struct RnpsRequest { uint64_t buffer; int32_t size; int32_t error; };
static_assert(sizeof(RnpsRequest) == 16);
static_assert(offsetof(RnpsRequest, size) == 8 && offsetof(RnpsRequest, error) == 12);
enum class BundleKind { Encrypted, HermesCandidate, JavaScriptCandidate, Unknown };
BundleKind classifyBundle(std::span<const std::byte>);
enum class IoctlResult { Completed, WrongDevice, UnknownRequest, BadAddress, BadSize, Unsupported, InvalidBundle };
struct GuestMemory {
    // Callbacks must copy through NovaFEX's validated guest address bridge. Never cast guest VAs.
    std::function<bool(uint64_t, std::span<std::byte>)> read;
    std::function<bool(uint64_t, std::span<const std::byte>)> write;
};
using BundleVerifier = std::function<bool(BundleKind, std::span<const std::byte>)>;
class RnpsIoctlHle {
public:
    explicit RnpsIoctlHle(BundleVerifier verifier) : verifier_(std::move(verifier)) {}
    IoctlResult handle(bool rnpsDescriptor, uint32_t request, uint64_t guestArgs, const GuestMemory&) const;
private:
    BundleVerifier verifier_;
};
} // namespace Nova::Dashboard
