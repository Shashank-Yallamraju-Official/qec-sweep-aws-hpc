// One pass over the amplitudes applying a gate in place: every index whose
// target bits are clear heads a group of 2^arity amplitudes the matrix mixes.
// bits[p] is the index bit of the matrix's p-th qubit, the first most significant.
#include <complex>
#include <cstdint>

extern "C" void mix(std::complex<double>* amplitudes, uint64_t length,
                    const std::complex<double>* matrix, int arity, const int* bits) {
    const int dim = 1 << arity;
    uint64_t targets = 0;
    for (int p = 0; p < arity; ++p) targets |= uint64_t(1) << bits[p];
    std::complex<double> in[4];
    uint64_t at[4];
    for (uint64_t head = 0; head < length; ++head) {
        if (head & targets) continue;
        for (int k = 0; k < dim; ++k) {
            uint64_t index = head;
            for (int p = 0; p < arity; ++p)
                if ((k >> (arity - 1 - p)) & 1) index |= uint64_t(1) << bits[p];
            at[k] = index;
            in[k] = amplitudes[index];
        }
        for (int r = 0; r < dim; ++r) {
            std::complex<double> sum = 0;
            for (int c = 0; c < dim; ++c) sum += matrix[r * dim + c] * in[c];
            amplitudes[at[r]] = sum;
        }
    }
}
