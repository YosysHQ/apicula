// chipdb.cpp - Chip database loading implementation
#include "chipdb.hpp"

#include <fstream>
#include <sstream>
#include <filesystem>
#include <iostream>
#include <zlib.h>

namespace apycula {

std::string find_chipdb(const std::string& device) {
    // Look for chipdb in common locations
    std::vector<std::string> paths = {
        device + ".msgpack.gz",
        "chipdb/" + device + ".msgpack.gz",
        "/usr/share/apycula/" + device + ".msgpack.gz",
        "/usr/local/share/apycula/" + device + ".msgpack.gz",
    };

    // Also check APYCULA_CHIPDB_DIR environment variable
    if (const char* env_path = std::getenv("APYCULA_CHIPDB_DIR")) {
        paths.insert(paths.begin(), std::string(env_path) + "/" + device + ".msgpack.gz");
    }

    for (const auto& path : paths) {
        if (std::filesystem::exists(path)) {
            return path;
        }
    }

    std::string msg = "Could not find chipdb for device: " + device + "\nSearched paths:\n";
    for (const auto& path : paths) {
        msg += "  " + path + "\n";
    }
    throw std::runtime_error(msg);
}

// Decompress gzip data
std::vector<uint8_t> decompress_gzip(const std::vector<uint8_t>& compressed) {
    z_stream strm{};
    if (inflateInit2(&strm, 16 + MAX_WBITS) != Z_OK) {
        throw std::runtime_error("Failed to initialize zlib");
    }

    std::vector<uint8_t> decompressed;
    decompressed.reserve(compressed.size() * 4);  // Estimate 4x compression ratio

    strm.next_in = const_cast<uint8_t*>(compressed.data());
    strm.avail_in = compressed.size();

    std::vector<uint8_t> buffer(16384);
    int ret;
    do {
        strm.next_out = buffer.data();
        strm.avail_out = buffer.size();
        ret = inflate(&strm, Z_NO_FLUSH);
        if (ret == Z_STREAM_ERROR || ret == Z_DATA_ERROR || ret == Z_MEM_ERROR) {
            inflateEnd(&strm);
            throw std::runtime_error("Zlib decompression error");
        }
        size_t have = buffer.size() - strm.avail_out;
        decompressed.insert(decompressed.end(), buffer.begin(), buffer.begin() + have);
    } while (ret != Z_STREAM_END);

    inflateEnd(&strm);
    return decompressed;
}

Device load_chipdb(const std::string& path) {
    // Read compressed file
    std::ifstream file(path, std::ios::binary);
    if (!file) {
        throw std::runtime_error("Could not open chipdb file: " + path);
    }

    std::vector<uint8_t> compressed(
        (std::istreambuf_iterator<char>(file)),
        std::istreambuf_iterator<char>());
    file.close();

    // Decompress
    auto data = decompress_gzip(compressed);

    // Deserialize with msgpack
    msgpack::object_handle oh = msgpack::unpack(
        reinterpret_cast<const char*>(data.data()), data.size());
    msgpack::object obj = oh.get();

    Device device;
    obj.convert(device);
    return device;
}

} // namespace apycula
