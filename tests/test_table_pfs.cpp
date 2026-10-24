#include "install.h"
#include "package/tablePfs.h"
#include <cstring>
#include <filesystem>
#include <fstream>
#include <functional>
#include <iostream>
#include <vector>
#include <zlib.h>
using B = std::vector<unsigned char>;
void put(B &b, size_t p, uint64_t v, size_t n) {
  for (size_t i = 0; i < n; i++)
    b.at(p + i) = v >> (8 * i);
}
void save(const std::string &p, const B &b) {
  std::ofstream f(p, std::ios::binary);
  f.write((const char *)b.data(), b.size());
}
B image(bool wide = false, bool fragmented = false) {
  const size_t bs = 4096, sb = bs * 5;
  B b(bs * 8);
  put(b, sb, 1, 8);
  put(b, sb + 8, 20130315, 8);
  put(b, sb + 0x1c, wide ? 3 : 0, 2);
  put(b, sb + 0x20, bs, 4);
  put(b, sb + 0x28, 8, 8);
  put(b, sb + 0x30, 2, 8);
  put(b, sb + 0x40, 1, 8);
  size_t stride = wide ? 0x310 : 0xa8, pw = wide ? 8 : 4,
         ptr = wide ? 0x88 : 0x64, ps = wide ? 40 : 4;
  auto node = [&](size_t i, int mode, size_t size, size_t block,
                  size_t blocks) {
    size_t r = sb + bs + i * stride;
    put(b, r, mode, 2);
    put(b, r + 8, size, 8);
    put(b, r + 0x10, size, 8);
    put(b, r + 0x60, blocks, pw);
    put(b, r + ptr, block, pw);
    put(b, r + ptr + ps, wide ? UINT64_MAX : UINT32_MAX, pw);
  };
  node(0, 0x4000, 32, 1, 1);
  node(1, 0x8000, fragmented ? 5000 : 20, 2, fragmented ? 2 : 1);
  if (fragmented)
    put(b, sb + bs + stride + ptr + ps, 4, pw);
  put(b, bs, 1, 4);
  put(b, bs + 4, 2, 4);
  put(b, bs + 8, 10, 4);
  put(b, bs + 12, 32, 4);
  memcpy(b.data() + bs + 16, "eboot.bin", 10);
  unsigned char elf[20] = {0x7f, 'E', 'L', 'F', 2, 1};
  elf[18] = 62;
  memcpy(b.data() + 2 * bs, elf, 20);
  return b;
}
int main() {
  namespace fs = std::filesystem;
  const std::string root = "/tmp/nova-table-tests";
  fs::remove_all(root);
  fs::create_directory(root);
  int failures = 0;
  auto run = [&](std::string name, B data, bool success, bool install = false) {
    auto src = root + "/" + name + ".pkg", dst = root + "/" + name;
    save(src, data);
    try {
      if (install) {
        fs::create_directory(dst);
        NovaPkg::Install(src, dst);
      } else
        NovaPkg::ExtractTablePfs(src, 0, data.size(), 5 * 4096, dst);
      if (!success)
        throw std::runtime_error("invalid fixture accepted");
      std::ifstream f(dst + (install ? "/pfs_files" : "") + "/eboot.bin",
                      std::ios::binary);
      char magic[4]{};
      f.read(magic, 4);
      if (memcmp(magic, "\177ELF", 4))
        throw std::runtime_error("wrong extracted bytes");
      std::cout << "PASS " << name << "\n";
    } catch (const std::exception &e) {
      if (success) {
        ++failures;
        std::cerr << "FAIL " << name << ": " << e.what() << "\n";
      } else
        std::cout << "PASS rejected " << name << "\n";
    }
  };
  run("plain", image(), true);
  run("signed64", image(true), true);
  run("fragmented", image(false, true), true);
  auto b = image();
  memcpy(b.data() + 4096 + 16, "../escape", 10);
  run("traversal", b, false);
  b = image();
  put(b, 4096 + 12, 8192, 4);
  run("bad-dir-span", b, false);
  b = image();
  put(b, 6 * 4096 + 0xa8 + 0x64, 99, 4);
  run("out-of-range", b, false);
  b = image();
  put(b, 5 * 4096 + 0x40, 0, 8);
  run("missing-table", b, false);
  b = image();
  put(b, 5 * 4096 + 0x1c, 4, 2);
  run("encrypted", b, false);
  b = image();
  put(b, 6 * 4096 + 0xa8 + 0x60, 0, 4);
  run("zero-blocks", b, false);
  // Data-first segments may put actual file data in physical block zero.
  b = image();
  std::copy(b.begin() + 2 * 4096, b.begin() + 3 * 4096, b.begin());
  put(b, 6 * 4096 + 0xa8 + 0x64, 0, 4);
  run("block-zero-contiguous", b, true);
  b = image(false, true);
  std::copy(b.begin() + 2 * 4096, b.begin() + 3 * 4096, b.begin());
  put(b, 6 * 4096 + 0xa8 + 0x64, 0, 4);
  run("block-zero-fragmented", b, true);
  // PFSC file decompression, including stored and compressed blocks.
  b = image();
  B compressed(4096, 0x5a);
  unsigned char elf[20] = {0x7f, 'E', 'L', 'F', 2, 1};
  elf[18] = 62;
  memcpy(compressed.data(), elf, 20);
  B z(8192);
  uLongf zs = z.size();
  compress2(z.data(), &zs, compressed.data(), compressed.size(), 6);
  z.resize(zs);
  size_t data = 2 * 4096, r = 6 * 4096 + 0xa8;
  put(b, r + 4, 1, 4);
  put(b, r + 8, 4096, 8);
  put(b, r + 0x10, 0x40 + zs, 8);
  put(b, data, 0x43534650, 4);
  put(b, data + 0xc, 4096, 4);
  put(b, data + 0x10, 4096, 8);
  put(b, data + 0x18, 0x30, 8);
  put(b, data + 0x20, 0x40, 8);
  put(b, data + 0x28, 4096, 8);
  put(b, data + 0x30, 0x40, 8);
  put(b, data + 0x38, 0x40 + zs, 8);
  std::copy(z.begin(), z.end(), b.begin() + data + 0x40);
  run("compressed", b, true);
  put(b, data + 0x38, UINT64_MAX, 8);
  run("bad-compressed-table", b, false);
  // A nested PFS is resolved via the outer table without carving or a spill
  // copy.
  B inner = image();
  std::copy(inner.begin() + 4096, inner.begin() + 2 * 4096,
            inner.begin() + 3 * 4096);
  put(inner, 6 * 4096 + 0x64, 3, 4);
  std::copy(inner.begin() + 5 * 4096, inner.begin() + 7 * 4096, inner.begin());
  b = image();
  b.resize(20 * 4096);
  put(b, 4096 + 8, 14, 4);
  memset(b.data() + 4096 + 16, 0, 16);
  memcpy(b.data() + 4096 + 16, "pfs_image.dat", 14);
  put(b, r + 8, inner.size(), 8);
  put(b, r + 0x10, inner.size(), 8);
  put(b, r + 0x60, 8, 4);
  put(b, r + 0x64, 8, 4);
  std::copy(inner.begin(), inner.end(), b.begin() + 8 * 4096);
  run("nested", b, true);
  // Complete data-first finalized package through the public installer.
  b = image();
  B pkg(0x10000 + b.size() + 0x10000);
  memcpy(pkg.data(), "\177FIH", 4);
  put(pkg, 0x10, 0x10000, 8);
  put(pkg, 0x18, b.size(), 8);
  put(pkg, 0x20, 0x10000 + 5 * 4096, 8);
  put(pkg, 0x58, 0x10000 + b.size(), 8);
  std::copy(b.begin(), b.end(), pkg.begin() + 0x10000);
  size_t cnt = 0x10000 + b.size();
  memcpy(pkg.data() + cnt, "\177CNT", 4);
  pkg[cnt + 0x26] = 2; // BE64 body offset = 0x200
  run("installer", pkg, true, true);
  return failures ? 1 : 0;
}
