#include "engine.h"

// engine.cpp is now just a thin entry point — the real class definitions
// live in engine.h so both this file and binding.cpp can include them
// without including a .cpp file into another .cpp file, which is bad
// practice in C++.
//
// A main() can be added here for standalone local testing of SpecIndex
// without going through Python at all, if useful during development.

int main() {
    return 0;
}