#ifndef SLIP_H
#define SLIP_H

#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>

bool slip_encode(
    const uint8_t *input,
    size_t input_len,
    uint8_t *output,
    size_t output_capacity,
    size_t *output_len
);

bool slip_decode(
    const uint8_t *input,
    size_t input_len,
    uint8_t *output,
    size_t output_capacity,
    size_t *output_len
);

#endif