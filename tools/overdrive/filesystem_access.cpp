// Copyright (C) 2026 half144 and PS5 React contributors
// SPDX-License-Identifier: GPL-3.0-or-later
// Additional attribution term: see upstream LICENSE-ATTRIBUTION.
// Nova guest adaptation: use the emulator's title sandbox without elevation.
#include "filesystem_access.hpp"
#include <cerrno>
#include <cstdio>
#include <cstring>
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

#ifndef NOVA_GUEST_APP_ROOT
#define NOVA_GUEST_APP_ROOT "/app0"
#define NOVA_GUEST_DATA_ROOT "/download0"
#define NOVA_GUEST_TEMP_ROOT "/temp0"
#endif

namespace {
bool ready = false;
bool directory(const char* path) {
  struct stat st{};
  return stat(path, &st) == 0 && S_ISDIR(st.st_mode);
}
bool writable(const char* root) {
  char path[1024];
  const int length = std::snprintf(path, sizeof path, "%s/.nova-overdrive-probe-%ld", root, long(getpid()));
  if (length < 0 || static_cast<std::size_t>(length) >= sizeof path) return false;
  const int fd = open(path, O_RDWR | O_CREAT | O_EXCL, 0600);
  if (fd < 0) return false;
  char readback = 0;
  bool ok = write(fd, "N", 1) == 1 && lseek(fd, 0, SEEK_SET) == 0 && read(fd, &readback, 1) == 1 && readback == 'N';
  if (close(fd) != 0) ok = false;
  if (unlink(path) != 0) ok = false;
  return ok;
}
bool inside(const char* path, const char* root) {
  const auto n = std::strlen(root);
  return std::strncmp(path, root, n) == 0 && (!path[n] || path[n] == '/');
}
}

void initialize_filesystem_access() {
  ready = false;
  if (!directory(NOVA_GUEST_APP_ROOT) || !directory(NOVA_GUEST_DATA_ROOT) ||
      !directory(NOVA_GUEST_TEMP_ROOT) || !writable(NOVA_GUEST_DATA_ROOT) || !writable(NOVA_GUEST_TEMP_ROOT)) {
    std::printf("[NOVA_OVERDRIVE] sandbox read/write proof failed errno=%d\n", errno);
    return;
  }
  const char* cache = NOVA_GUEST_DATA_ROOT "/.cache";
  if ((mkdir(cache, 0700) != 0 && errno != EEXIST) || !directory(cache) || !writable(cache)) return;
  ready = true;
  std::printf("[NOVA_OVERDRIVE] title sandbox ready; no console elevation requested\n");
}

bool resolve_filesystem_path(const char* path, char* out, std::size_t size) {
  if (!path || !out || !size || path[0] != '/') return false;
  for (const char* p = path; *p;) {
    while (*p == '/') ++p;
    const char* begin = p;
    while (*p && *p != '/') ++p;
    if (p - begin == 2 && begin[0] == '.' && begin[1] == '.') return false;
  }
  const char* logical[] = {"/cache0", "/app0", "/download0", "/temp0", "/data"};
  const char* physical[] = {NOVA_GUEST_DATA_ROOT "/.cache", NOVA_GUEST_APP_ROOT,
                            NOVA_GUEST_DATA_ROOT, NOVA_GUEST_TEMP_ROOT, NOVA_GUEST_DATA_ROOT};
  for (unsigned i = 0; i < sizeof logical / sizeof *logical; ++i) {
    if (!inside(path, logical[i])) continue;
    const int n = std::snprintf(out, size, "%s%s", physical[i], path + std::strlen(logical[i]));
    return n >= 0 && static_cast<std::size_t>(n) < size;
  }
  return false;
}

// This means access to the title's own mapped storage, never console credentials.
bool console_filesystem_accessible() { return ready; }
