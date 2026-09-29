#include <pybind11/pybind11.h>
#include "engine.h"

namespace py = pybind11;

// Module name chosen as "spec_engine" — this is literally what gets typed
// in Python: `import spec_engine`. Must match the compiled output filename
// (spec_engine.so / spec_engine.pyd), which the build step handles.
PYBIND11_MODULE(spec_engine, m) {

    // Exposing SpecPoint's constructor signature explicitly — Python has
    // no visibility into C++ constructors unless told about them here.
    // Types/order must match the real constructor in engine.h exactly:
    // SpecPoint(string tag, string description, string subject, string exam_board)
    py::class_<SpecPoint>(m, "SpecPoint")
        .def(py::init<string, string, string, string>())
        // read-only, not read-write — a spec point's fields are set once
        // at creation and shouldn't be mutable from Python afterward
        .def_readonly("tag", &SpecPoint::tag)
        .def_readonly("description", &SpecPoint::description)
        .def_readonly("subject", &SpecPoint::subject)
        .def_readonly("exam_board", &SpecPoint::exam_board);

    // SpecIndex never got a custom constructor in C++, so it has an
    // implicit default (no-argument) one. Python still needs an explicit
    // binding to be allowed to call it — py::init<>() exposes that default.
    py::class_<SpecIndex>(m, "SpecIndex")
        .def(py::init<>())
        .def("addPoint", &SpecIndex::addPoint)
        .def("search", &SpecIndex::search);
        // No manual exception handling needed here — pybind11 automatically
        // converts SpecIndex::search()'s std::runtime_error throw into a
        // catchable Python RuntimeError on the other side.
}