#include "RnpsIoctlHle.h"
#include <array>
#include <bit>
#include <cstring>
#include <limits>
#include <vector>

namespace Nova::Dashboard {
BundleKind classifyBundle(std::span<const std::byte> b) {
    if (b.size() >= 8 && std::memcmp(b.data(), "RNPSHEDR", 8) == 0) return BundleKind::Encrypted;
    constexpr unsigned char hermes[] = {0xc6, 0x1f, 0xbc, 0x03, 0xc1, 0x03, 0x19, 0x1f};
    if (b.size() >= 8 && std::memcmp(b.data(), hermes, 8) == 0) return BundleKind::HermesCandidate;
    // Text detection is a hint only. The runtime-supplied verifier is mandatory before success.
    if (!b.empty()) {
        for (const auto byte : b) {
            const auto c = std::to_integer<unsigned char>(byte);
            if (c == 0 || (c < 32 && c != '\n' && c != '\r' && c != '\t')) return BundleKind::Unknown;
        }
        return BundleKind::JavaScriptCandidate;
    }
    return BundleKind::Unknown;
}
IoctlResult RnpsIoctlHle::handle(bool rnps, uint32_t request, uint64_t arg, const GuestMemory& mem) const {
    static_assert(std::endian::native == std::endian::little);
    if (!rnps) return IoctlResult::WrongDevice;
    if (request != VerifyDecryptRnpsBundle) return IoctlResult::UnknownRequest;
    if (!mem.read || !mem.write || !arg || arg > UINT64_MAX - sizeof(RnpsRequest)) return IoctlResult::BadAddress;
    RnpsRequest args{};
    if (!mem.read(arg, std::as_writable_bytes(std::span(&args, 1)))) return IoctlResult::BadAddress;
    constexpr int32_t limit = 64 * 1024 * 1024;
    if (args.size <= 0 || args.size > limit) return IoctlResult::BadSize;
    if (!args.buffer || args.buffer > UINT64_MAX - static_cast<uint32_t>(args.size)) return IoctlResult::BadAddress;
    const auto end = args.buffer + static_cast<uint32_t>(args.size);
    if (args.buffer < arg + sizeof(args) && arg < end) return IoctlResult::BadAddress;
    std::vector<std::byte> snapshot(static_cast<size_t>(args.size));
    if (!mem.read(args.buffer, snapshot)) return IoctlResult::BadAddress;
    const auto kind = classifyBundle(snapshot);
    if (kind == BundleKind::Encrypted || kind == BundleKind::Unknown || !verifier_) return IoctlResult::Unsupported;
    if (!verifier_(kind, snapshot)) return IoctlResult::InvalidBundle;
    // Plaintext passthrough, not decryption. Only the observed error field is written.
    const int32_t success = 0;
    if (!mem.write(arg + offsetof(RnpsRequest, error), std::as_bytes(std::span(&success, 1))))
        return IoctlResult::BadAddress;
    return IoctlResult::Completed;
}
} // namespace Nova::Dashboard
