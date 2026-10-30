// One pass over the amplitudes applying a gate in place. The indices whose
// target bits are clear head the groups of 2^arity amplitudes the matrix
// mixes; the pass walks those heads only. A diagonal gate scales each member
// of a group on its own, so the pass touches only the amplitudes it changes.
// bits[p] is the index bit of the matrix's p-th qubit, the first most significant.
// Only members whose index has keep_value under keep_mask are written: a rank
// that stacked other ranks' slices with its own keeps its own row of the result.
#include <complex>
#include <cstdint>

using amplitude = std::complex<double>;

// Written out so the compiler need not guard against infinities the way
// std::complex's operator* does; a state vector has none.
static inline amplitude times(amplitude a, amplitude b) {
    return {a.real() * b.real() - a.imag() * b.imag(), a.real() * b.imag() + a.imag() * b.real()};
}

// The i-th index with a zero inserted at each of the ascending bits: a group's head.
template <int ARITY>
static inline uint64_t head_of(uint64_t i, const int (&ascending)[ARITY]) {
    for (int p = 0; p < ARITY; ++p) {
        const uint64_t low = (uint64_t(1) << ascending[p]) - 1;
        i = ((i & ~low) << 1) | (i & low);
    }
    return i;
}

template <int ARITY>
struct Layout {
    static constexpr int DIM = 1 << ARITY;
    int ascending[ARITY];
    uint64_t offset[DIM];  // of each group member from its head
    uint64_t kept[DIM];    // the member's offset under keep_mask
    uint64_t keep_mask, keep_value;

    Layout(const int* bits, uint64_t mask, uint64_t value) : keep_mask(mask), keep_value(value) {
        for (int p = 0; p < ARITY; ++p) ascending[p] = bits[p];
        if constexpr (ARITY == 2) {
            if (ascending[0] > ascending[1]) {
                const int swap = ascending[0];
                ascending[0] = ascending[1];
                ascending[1] = swap;
            }
        }
        for (int k = 0; k < DIM; ++k) {
            offset[k] = 0;
            for (int p = 0; p < ARITY; ++p)
                if ((k >> (ARITY - 1 - p)) & 1) offset[k] |= uint64_t(1) << bits[p];
            kept[k] = offset[k] & keep_mask;
        }
    }

    // Whether member k of the group at head is written: its index, under the mask, is the kept value.
    bool keeps(uint64_t head, int k) const { return ((head & keep_mask) | kept[k]) == keep_value; }
};

template <int ARITY>
static void mix_dense(amplitude* a, uint64_t length, const amplitude* m, const Layout<ARITY>& layout) {
    constexpr int DIM = 1 << ARITY;
    const uint64_t groups = length >> ARITY;
    for (uint64_t g = 0; g < groups; ++g) {
        const uint64_t head = head_of<ARITY>(g, layout.ascending);
        if ((head & layout.keep_mask & ~layout.kept[DIM - 1]) != (layout.keep_value & ~layout.kept[DIM - 1]))
            continue;  // no member of this group is kept
        amplitude in[DIM];
        for (int k = 0; k < DIM; ++k) in[k] = a[head + layout.offset[k]];
        for (int r = 0; r < DIM; ++r) {
            if (!layout.keeps(head, r)) continue;
            amplitude sum = 0;
            for (int c = 0; c < DIM; ++c) sum += times(m[r * DIM + c], in[c]);
            a[head + layout.offset[r]] = sum;
        }
    }
}

template <int ARITY>
static void mix_diagonal(amplitude* a, uint64_t length, const amplitude* m, const Layout<ARITY>& layout) {
    constexpr int DIM = 1 << ARITY;
    const uint64_t groups = length >> ARITY;
    for (int k = 0; k < DIM; ++k) {
        const amplitude phase = m[k * DIM + k];
        if (phase == amplitude(1)) continue;
        for (uint64_t g = 0; g < groups; ++g) {
            const uint64_t head = head_of<ARITY>(g, layout.ascending);
            if (!layout.keeps(head, k)) continue;
            amplitude& member = a[head + layout.offset[k]];
            member = times(member, phase);
        }
    }
}

static bool diagonal(const amplitude* m, int dim) {
    for (int r = 0; r < dim; ++r)
        for (int c = 0; c < dim; ++c)
            if (r != c && m[r * dim + c] != amplitude(0)) return false;
    return true;
}

template <int ARITY>
static void mix_as(amplitude* a, uint64_t length, const amplitude* m, const int* bits,
                   uint64_t keep_mask, uint64_t keep_value) {
    const Layout<ARITY> layout(bits, keep_mask, keep_value);
    if (diagonal(m, 1 << ARITY)) mix_diagonal<ARITY>(a, length, m, layout);
    else mix_dense<ARITY>(a, length, m, layout);
}

extern "C" void mix(amplitude* amplitudes, uint64_t length, const amplitude* matrix, int arity,
                    const int* bits, uint64_t keep_mask, uint64_t keep_value) {
    if (arity == 1) mix_as<1>(amplitudes, length, matrix, bits, keep_mask, keep_value);
    else mix_as<2>(amplitudes, length, matrix, bits, keep_mask, keep_value);
}
