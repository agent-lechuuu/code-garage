#!/usr/bin/env bash
# Writes the fixture project into the empty workspace (files only).
set -euo pipefail
cat > 'CMakeLists.txt' <<'GARAGE_EOF'
cmake_minimum_required(VERSION 3.20)
project(capture CXX)
set(CMAKE_CXX_STANDARD 20)
find_package(Threads REQUIRED)
add_executable(capture src/main.cpp)
target_link_libraries(capture Threads::Threads)
GARAGE_EOF
mkdir -p 'src'
cat > 'src/main.cpp' <<'GARAGE_EOF'
#include <mutex>
#include <queue>
#include <thread>
#include <vector>
#include <cstdint>

struct Frame { std::vector<uint8_t> data; int64_t pts; };

std::mutex mu;
std::queue<Frame> frames;

void capture() {
  for (int64_t i = 0;; ++i) {
    Frame f{std::vector<uint8_t>(1920 * 1080), i};
    std::lock_guard<std::mutex> lock(mu);
    frames.push(std::move(f));
  }
}

void encode() {
  for (;;) {
    std::lock_guard<std::mutex> lock(mu);
    if (frames.empty()) continue;
    Frame f = std::move(frames.front());
    frames.pop();
    // encode f ...
  }
}

int main() {
  std::thread a(capture), b(encode);
  a.join();
  b.join();
}
GARAGE_EOF
