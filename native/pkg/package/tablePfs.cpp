// SPDX-License-Identifier: GPL-2.0-or-later
// Nova Android table-based PFS extraction; format approach adapted from
// KytyPlus GameImage.cs (MIT), Copyright retained in TABLE-PFS-SOURCES.md.
#include "tablePfs.h"
#include <algorithm>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <functional>
#include <map>
#include <memory>
#include <set>
#include <stdexcept>
#include <vector>
#include <zlib.h>
namespace NovaPkg {
namespace {
using Bytes = std::vector<uint8_t>;
[[noreturn]] void Bad(const char *s) {
  throw std::runtime_error(std::string("PKG filesystem: ") + s);
}
void Range(uint64_t total, uint64_t off, uint64_t size) {
  if (off > total || size > total - off)
    Bad("extent outside image");
}
uint64_t Add(uint64_t a, uint64_t b) {
  if (b > UINT64_MAX - a)
    Bad("offset overflow");
  return a + b;
}
uint64_t Mul(uint64_t a, uint64_t b) {
  if (a && b > UINT64_MAX / a)
    Bad("size overflow");
  return a * b;
}
uint64_t LE(const Bytes &b, size_t p, size_t n) {
  Range(b.size(), p, n);
  uint64_t v = 0;
  for (size_t i = 0; i < n; i++)
    v |= uint64_t(b[p + i]) << (i * 8);
  return v;
}
struct Image {
  uint64_t size;
  std::function<void(uint64_t, size_t, uint8_t *)> reader;
  void read(uint64_t off, size_t n, uint8_t *dst) const {
    Range(size, off, n);
    reader(off, n, dst);
  }
  Bytes bytes(uint64_t off, size_t n) const {
    if (n > 128 * 1024 * 1024)
      Bad("metadata allocation too large");
    Bytes b(n);
    read(off, n, b.data());
    return b;
  }
};
using Img = std::shared_ptr<Image>;
Img Slice(Img src, uint64_t start, uint64_t size) {
  Range(src->size, start, size);
  return std::make_shared<Image>(
      Image{size, [src, start](uint64_t o, size_t n, uint8_t *d) {
              src->read(Add(start, o), n, d);
            }});
}
Img File(const std::string &path) {
  auto f = std::make_shared<std::ifstream>(path, std::ios::binary);
  if (!*f)
    Bad("cannot open source");
  auto size = std::filesystem::file_size(path);
  return std::make_shared<Image>(
      Image{size, [f](uint64_t o, size_t n, uint8_t *d) {
              f->clear();
              f->seekg(o);
              f->read(reinterpret_cast<char *>(d), n);
              if (size_t(f->gcount()) != n)
                Bad("truncated source");
            }});
}
Img Chain(Img src, const std::vector<uint64_t> &blocks, uint64_t bs,
          uint64_t size) {
  Range(Mul(blocks.size(), bs), 0, size);
  return std::make_shared<Image>(
      Image{size, [src, blocks, bs](uint64_t off, size_t n, uint8_t *d) {
              while (n) {
                size_t take = std::min<uint64_t>(n, bs - off % bs);
                src->read(Add(Mul(blocks.at(off / bs), bs), off % bs), take, d);
                off += take;
                d += take;
                n -= take;
              }
            }});
}
Img Pfsc(Img src) {
  auto h = src->bytes(0, 0x30);
  if (LE(h, 0, 4) != 0x43534650)
    Bad("missing PFSC signature");
  uint64_t bs = LE(h, 0xc, 4), size = LE(h, 0x28, 8), table = LE(h, 0x18, 8),
           data = LE(h, 0x20, 8);
  if (bs < 4096 || bs > 0x100000 || (bs & (bs - 1)) || LE(h, 0x10, 8) != bs ||
      !size)
    Bad("invalid PFSC geometry");
  uint64_t count = Add(size, bs - 1) / bs;
  if (count > 16000000)
    Bad("PFSC table too large");
  auto tb = src->bytes(table, Mul(count + 1, 8));
  if (table < 0x30 || data < Add(table, tb.size()))
    Bad("overlapping PFSC table");
  auto offsets = std::make_shared<std::vector<uint64_t>>();
  for (uint64_t i = 0; i <= count; i++) {
    auto o = LE(tb, i * 8, 8);
    if (o > src->size || (!i && o != data) ||
        (i && (o <= offsets->back() || o - offsets->back() > bs)))
      Bad("invalid PFSC offset");
    offsets->push_back(o);
  }
  return std::make_shared<Image>(
      Image{size, [src, offsets, bs](uint64_t off, size_t n, uint8_t *d) {
              while (n) {
                auto idx = off / bs;
                auto stored = src->bytes(
                    offsets->at(idx), offsets->at(idx + 1) - offsets->at(idx));
                Bytes decoded(bs);
                if (stored.size() == bs)
                  decoded = std::move(stored);
                else {
                  uLongf len = bs;
                  if (uncompress(decoded.data(), &len, stored.data(),
                                 stored.size()) != Z_OK ||
                      len != bs)
                    Bad("invalid PFSC compressed block");
                }
                size_t take = std::min<uint64_t>(n, bs - off % bs);
                memcpy(d, decoded.data() + off % bs, take);
                off += take;
                d += take;
                n -= take;
              }
            }});
}
void Name(const std::string &n) {
  if (n.empty() || n == "." || n == ".." || n.size() > 255)
    Bad("unsafe filename");
  for (unsigned char c : n)
    if (c < 32 || c == '/' || c == '\\' || c == ':' || c == 0)
      Bad("unsafe filename");
}
struct Entry {
  std::string path;
  Img data;
};
struct Node {
  uint16_t mode;
  uint32_t flags;
  uint64_t size, logical, blocks;
  Bytes rec;
};
class Tree {
  Img image;
  uint64_t bs;
  size_t stride, pw, po, ps;
  bool sign;
  std::vector<Node> nodes;
  std::set<uint32_t> visited;
  std::set<std::string> names;
  uint64_t ptr(const Bytes &r, size_t i) { return LE(r, i, pw); }
  Img Data(uint32_t index) {
    const auto &n = nodes.at(index);
    if (!n.size)
      return Slice(image, 0, 0);
    if (!n.blocks || n.blocks > 16000000 || n.blocks > image->size / bs)
      Bad("invalid file block count");
    uint64_t storedSize = (n.flags & 1) ? n.logical : n.size;
    if (!storedSize)
      Bad("missing stored file size");
    size_t p = po + (sign ? 32 : 0);
    auto first = ptr(n.rec, p), second = ptr(n.rec, p + ps);
    bool contiguous =
        n.blocks <= 1 || second == (pw == 8 ? UINT64_MAX : UINT32_MAX);
    Img stored;
    if (contiguous) {
      Range(image->size, Mul(first, bs), Mul(n.blocks, bs));
      Range(Mul(n.blocks, bs), 0, storedSize);
      stored = Slice(image, Mul(first, bs), storedSize);
    } else {
      std::vector<uint64_t> blocks;
      std::set<uint64_t> seen;
      auto add = [&](uint64_t b) {
        Range(image->size, Mul(b, bs), bs);
        blocks.push_back(b);
      };
      for (size_t i = 0; i < 12 && blocks.size() < n.blocks; i++)
        add(ptr(n.rec, p + i * ps));
      std::function<void(uint64_t, int)> indirect = [&](uint64_t block,
                                                        int depth) {
        if (!seen.insert(block).second)
          Bad("cyclic indirect chain");
        auto b = image->bytes(Mul(block, bs), bs);
        for (size_t pos = 0; pos + ps <= b.size() && blocks.size() < n.blocks;
             pos += ps) {
          auto next = ptr(b, pos + (sign ? 32 : 0));
          if (depth == 1)
            add(next);
          else
            indirect(next, depth - 1);
        }
      };
      for (int i = 0; i < 5 && blocks.size() < n.blocks; i++)
        indirect(ptr(n.rec, p + (12 + i) * ps), i + 1);
      if (blocks.size() != n.blocks)
        Bad("truncated block chain");
      stored = Chain(image, blocks, bs, storedSize);
    }
    if (!(n.flags & 1))
      return stored;
    auto decoded = Pfsc(stored);
    if (decoded->size != n.size)
      Bad("PFSC logical size differs from inode");
    return decoded;
  }
  struct Dir {
    std::string name;
    uint32_t inode, type;
  };
  std::vector<Dir> Directory(uint32_t ino) {
    if (ino >= nodes.size() || (nodes[ino].mode & 0xf000) != 0x4000 ||
        nodes[ino].size > 16 * 1024 * 1024)
      Bad("invalid directory inode");
    auto src = Data(ino);
    auto b = src->bytes(0, src->size);
    std::vector<Dir> out;
    size_t p = 0;
    while (p + 16 <= b.size()) {
      uint32_t child = LE(b, p, 4), type = LE(b, p + 4, 4),
               len = LE(b, p + 8, 4), span = LE(b, p + 12, 4);
      if (!span) {
        for (size_t k = p; k < b.size(); k++)
          if (b[k])
            Bad("nonzero directory padding");
        break;
      }
      if (span < 16 || span > b.size() - p || !len || len > span - 16 ||
          len > 256 || child >= nodes.size())
        Bad("invalid directory record");
      std::string name(reinterpret_cast<const char *>(b.data() + p + 16), len);
      if (!name.empty() && name.back() == 0)
        name.pop_back();
      if (type == 2 || type == 3) {
        Name(name);
        out.push_back({name, child, type});
      } else if (type != 4 && type != 5)
        Bad("unknown directory entry");
      p += span;
    }
    return out;
  }
  void Walk(uint32_t ino, const std::string &prefix, int depth) {
    if (depth > 64 || !visited.insert(ino).second)
      Bad("cyclic/deep directory tree");
    for (const auto &e : Directory(ino)) {
      auto path = prefix + e.name;
      if (!names.insert(path).second)
        Bad("duplicate path");
      if (e.type == 3)
        Walk(e.inode, path + "/", depth + 1);
      else {
        if ((nodes[e.inode].mode & 0xf000) != 0x8000)
          Bad("file entry references non-file");
        files.push_back({path, Data(e.inode)});
        if (files.size() > 1000000)
          Bad("too many files");
      }
    }
  }

public:
  std::vector<Entry> files;
  Tree(Img img, uint64_t super) : image(img) {
    auto h = img->bytes(super, 0x380);
    auto version = LE(h, 0, 8);
    if ((version != 1 && version != 2) || LE(h, 8, 8) != 20130315)
      Bad("unsupported PFS superblock");
    auto mode = LE(h, 0x1c, 2);
    bool patched = memcmp(h.data() + 0x370, "PPRPLAIN-NOAUTH!", 16) == 0;
    if ((mode & 4) && !patched)
      Bad("encrypted PFS data");
    sign = mode & 1;
    bool wide = mode & 2;
    if (wide && !sign)
      Bad("unsigned wide inode format");
    stride = sign ? (wide ? 0x310 : 0x2c8) : 0xa8;
    pw = wide ? 8 : 4;
    po = wide ? 0x68 : 0x64;
    ps = pw + (sign ? 32 : 0);
    bs = LE(h, 0x20, 4);
    auto count = LE(h, 0x30, 8), tableBlocks = LE(h, 0x40, 8);
    if (bs < 4096 || bs > 0x100000 || (bs & (bs - 1)) || !count ||
        count > 1000000)
      Bad("invalid PFS geometry");
    auto per = bs / stride, needed = (count + per - 1) / per;
    if (tableBlocks < needed || Mul(needed, bs) > 128 * 1024 * 1024)
      Bad("invalid inode table extent");
    auto table = img->bytes(Add(super, bs), Mul(needed, bs));
    for (uint64_t i = 0; i < count; i++) {
      auto p = i / per * bs + i % per * stride;
      Bytes r(table.begin() + p, table.begin() + p + stride);
      nodes.push_back({uint16_t(LE(r, 0, 2)), uint32_t(LE(r, 4, 4)),
                       LE(r, 8, 8), LE(r, 0x10, 8), LE(r, 0x60, pw),
                       std::move(r)});
    }
    auto entries = Directory(0);
    uint32_t root = 0;
    for (auto &e : entries)
      if (e.name == "uroot" && e.type == 3)
        root = e.inode;
    Walk(root, "", 0);
  }
};
std::vector<Entry> ReadTree(Img image, uint64_t super, int depth) {
  if (depth > 4)
    Bad("too many nested images");
  auto h = image->bytes(0, 16);
  if (!super && LE(h, 0, 4) == 0x43534650)
    return ReadTree(Pfsc(image), 0, depth + 1);
  Tree tree(image, super);
  Img nested;
  for (auto &e : tree.files)
    if (e.path == "pfs_image.dat") {
      if (nested)
        Bad("ambiguous nested image");
      nested = e.data;
    }
  return nested ? ReadTree(nested, 0, depth + 1) : tree.files;
}
} // namespace
uint32_t ExtractTablePfs(const std::string &path, uint64_t base, uint64_t size,
                         uint64_t superblock, const std::string &output) {
  auto source = File(path);
  auto image = Slice(source, base, size);
  if (superblock < base)
    Bad("superblock before segment");
  auto files = ReadTree(image, superblock - base, 0);
  if (files.empty())
    Bad("empty game filesystem");
  namespace fs = std::filesystem;
  fs::create_directories(output);
  if (!fs::is_empty(output))
    Bad("output must be empty");
  Bytes buf(1024 * 1024);
  uint32_t count = 0;
  for (auto &e : files) {
    fs::path relative(e.path);
    if (relative.is_absolute())
      Bad("absolute file path");
    auto dest = fs::path(output) / relative;
    fs::create_directories(dest.parent_path());
    std::ofstream out(dest, std::ios::binary | std::ios::trunc);
    if (!out)
      Bad("cannot create output file");
    for (uint64_t pos = 0; pos < e.data->size;) {
      size_t take = std::min<uint64_t>(buf.size(), e.data->size - pos);
      e.data->read(pos, take, buf.data());
      out.write(reinterpret_cast<const char *>(buf.data()), take);
      if (!out)
        Bad("output write failed (storage full?)");
      pos += take;
    }
    out.close();
    if (!out || fs::file_size(dest) != e.data->size)
      Bad("incomplete output file");
    ++count;
  }
  return count;
}
} // namespace NovaPkg
