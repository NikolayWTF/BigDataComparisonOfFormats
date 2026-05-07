#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <fstream>
#include <string>

namespace py = pybind11;

size_t count_lines(const std::string& path) {
    std::ifstream file(path);

    if (!file.is_open()) {
        throw std::runtime_error("Cannot open file: " + path);
    }

    size_t count = 0;
    std::string line;

    while (std::getline(file, line)) {
        ++count;
    }

    return count;
}

PYBIND11_MODULE(fast_count, m) {
    m.doc() = "Simple C++ binding for fast line counting";
    m.def("count_lines", &count_lines, "Count lines in a file");
}
