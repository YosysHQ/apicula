// chipdb_adaptors.hpp - msgpack-c adaptors for tuple/array/set keys
// These adaptors tell msgpack-c how to deserialize Python types from msgpack
#pragma once

#include <msgpack.hpp>
#include <array>
#include <utility>
#include <tuple>
#include <set>
#include <map>
#include <optional>

namespace msgpack {
MSGPACK_API_VERSION_NAMESPACE(MSGPACK_DEFAULT_API_NS) {
namespace adaptor {

// Deserialize msgpack array [a, b] -> std::pair<T, U>
template<typename T, typename U>
struct convert<std::pair<T, U>> {
    msgpack::object const& operator()(msgpack::object const& o, std::pair<T, U>& v) const {
        if (o.type != msgpack::type::ARRAY || o.via.array.size != 2) {
            throw msgpack::type_error();
        }
        v.first = o.via.array.ptr[0].as<T>();
        v.second = o.via.array.ptr[1].as<U>();
        return o;
    }
};

// Serialize std::pair<T, U> -> msgpack array [a, b]
template<typename T, typename U>
struct pack<std::pair<T, U>> {
    template <typename Stream>
    msgpack::packer<Stream>& operator()(msgpack::packer<Stream>& o, const std::pair<T, U>& v) const {
        o.pack_array(2);
        o.pack(v.first);
        o.pack(v.second);
        return o;
    }
};

// Deserialize msgpack array -> std::array<T, N>
template<typename T, size_t N>
struct convert<std::array<T, N>> {
    msgpack::object const& operator()(msgpack::object const& o, std::array<T, N>& v) const {
        if (o.type != msgpack::type::ARRAY || o.via.array.size != N) {
            throw msgpack::type_error();
        }
        for (size_t i = 0; i < N; ++i) {
            v[i] = o.via.array.ptr[i].as<T>();
        }
        return o;
    }
};

// Serialize std::array<T, N> -> msgpack array
template<typename T, size_t N>
struct pack<std::array<T, N>> {
    template <typename Stream>
    msgpack::packer<Stream>& operator()(msgpack::packer<Stream>& o, const std::array<T, N>& v) const {
        o.pack_array(N);
        for (const auto& elem : v) {
            o.pack(elem);
        }
        return o;
    }
};

// Helper for tuple deserialization
template<typename Tuple, size_t... Is>
void convert_tuple_impl(msgpack::object const& o, Tuple& t, std::index_sequence<Is...>) {
    ((std::get<Is>(t) = o.via.array.ptr[Is].as<std::tuple_element_t<Is, Tuple>>()), ...);
}

// Deserialize msgpack array -> std::tuple<Args...>
template<typename... Args>
struct convert<std::tuple<Args...>> {
    msgpack::object const& operator()(msgpack::object const& o, std::tuple<Args...>& v) const {
        if (o.type != msgpack::type::ARRAY || o.via.array.size != sizeof...(Args)) {
            throw msgpack::type_error();
        }
        convert_tuple_impl(o, v, std::index_sequence_for<Args...>{});
        return o;
    }
};

// Helper for tuple serialization
template<typename Tuple, typename Stream, size_t... Is>
void pack_tuple_impl(msgpack::packer<Stream>& o, const Tuple& t, std::index_sequence<Is...>) {
    ((o.pack(std::get<Is>(t))), ...);
}

// Serialize std::tuple<Args...> -> msgpack array
template<typename... Args>
struct pack<std::tuple<Args...>> {
    template <typename Stream>
    msgpack::packer<Stream>& operator()(msgpack::packer<Stream>& o, const std::tuple<Args...>& v) const {
        o.pack_array(sizeof...(Args));
        pack_tuple_impl(o, v, std::index_sequence_for<Args...>{});
        return o;
    }
};

// Deserialize msgpack array -> std::set<T>
template<typename T>
struct convert<std::set<T>> {
    msgpack::object const& operator()(msgpack::object const& o, std::set<T>& v) const {
        if (o.type != msgpack::type::ARRAY) {
            throw msgpack::type_error();
        }
        v.clear();
        for (size_t i = 0; i < o.via.array.size; ++i) {
            v.insert(o.via.array.ptr[i].as<T>());
        }
        return o;
    }
};

// Serialize std::set<T> -> msgpack array
template<typename T>
struct pack<std::set<T>> {
    template <typename Stream>
    msgpack::packer<Stream>& operator()(msgpack::packer<Stream>& o, const std::set<T>& v) const {
        o.pack_array(v.size());
        for (const auto& elem : v) {
            o.pack(elem);
        }
        return o;
    }
};

// Deserialize msgpack nil/value -> std::optional<T>
template<typename T>
struct convert<std::optional<T>> {
    msgpack::object const& operator()(msgpack::object const& o, std::optional<T>& v) const {
        if (o.type == msgpack::type::NIL) {
            v = std::nullopt;
        } else {
            v = o.as<T>();
        }
        return o;
    }
};

// Serialize std::optional<T> -> msgpack nil/value
template<typename T>
struct pack<std::optional<T>> {
    template <typename Stream>
    msgpack::packer<Stream>& operator()(msgpack::packer<Stream>& o, const std::optional<T>& v) const {
        if (v) {
            o.pack(*v);
        } else {
            o.pack_nil();
        }
        return o;
    }
};

} // namespace adaptor
} // MSGPACK_API_VERSION_NAMESPACE
} // namespace msgpack
