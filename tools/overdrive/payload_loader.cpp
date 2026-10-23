// Copyright (C) 2026 half144 and PS5 React contributors
// SPDX-License-Identifier: GPL-3.0-or-later
// Additional attribution term: see upstream LICENSE-ATTRIBUTION.
// Nova owns the guest process. There is no external console ELF-loader service.
#include "payload_loader.hpp"

namespace payload_loader {
int send(const char*, const std::string&, int, const char* what, std::string& error) {
  error = std::string(what) + ": console payload services are unavailable in the Nova guest profile";
  return -1;
}
int receive(int, char*, std::size_t) { return -1; }
bool write(int, const char*, std::size_t) { return false; }
void receive_timeout(int, int) {}
void close(int) {}
}
