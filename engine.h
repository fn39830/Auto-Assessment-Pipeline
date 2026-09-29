#ifndef ENGINE_H
#define ENGINE_H

#include <string>
#include <vector>
#include <stdexcept>
using namespace std;

// Simple data container for one exam board spec point (e.g. Physics 5.1.2).
// struct over class here since there's no behaviour to encapsulate — it's
// just fields set once and read many times, so public access by default
// is the right fit rather than fighting the language's convention.
struct SpecPoint {
    string tag;          // e.g. "5.1.2"
    string description;  // short text describing what the spec point covers
    // Storing subject/exam_board as their own fields rather than parsing them
    // out of a combined tag string later — splitting strings in C++ is a lot
    // more manual than Python's .split(), so it's easier to just keep them
    // separate from the start.
    string subject;
    string exam_board;

    SpecPoint(string tag, string description, string subject, string exam_board) {
        // this-> needed here specifically because the constructor params share
        // names with the member variables — without it, e.g. "tag = tag;" would
        // just assign the parameter to itself and silently do nothing.
        this->tag = tag;
        this->description = description;
        this->subject = subject;
        this->exam_board = exam_board;
    }
};

// Holds the full collection of spec points and handles lookup by tag.
// class rather than struct, because unlike SpecPoint it's actually
// encapsulating something — the vector is private, so nothing outside
// this class can mutate it directly. That keeps the door open to add
// validation later (e.g. rejecting duplicate tags) without breaking
// anything that already depends on this class.
class SpecIndex {
private:
    vector<SpecPoint> points;  // no guarantee this is sorted, hence linear search below

public:
    void addPoint(SpecPoint point) {
        points.push_back(point);
    }

    // Linear search, O(n) worst case. Data isn't sorted, so binary search
    // isn't an option as-is. If this ends up being a bottleneck once the
    // dataset grows, the fix is to sort once with std::sort and switch to
    // binary search (O(log n)) — not worth the added complexity yet.
    SpecPoint search(string tag) {
        for (int i = 0; i < points.size(); i++) {
            if (points[i].tag == tag) {
                return points[i];
            }
        }
        // Throw rather than print — a failed lookup must interrupt
        // execution and be explicitly handled by the caller, not
        // silently ignored. Pybind11 auto-converts this into a Python
        // RuntimeError on the other side, so it stays catchable there too.
        throw runtime_error("Spec tag not found: " + tag);
    }
};

#endif