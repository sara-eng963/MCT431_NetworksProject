#include "slip.h"

#define SLIP_END     0xC0
#define SLIP_ESC     0xDB
#define SLIP_ESC_END 0xDC
#define SLIP_ESC_ESC 0xDD

bool slip_encode(
    const uint8_t *input,
    size_t input_len,
    uint8_t *output,
    size_t output_capacity,
    size_t *output_len)
{
    if (!input || !output || !output_len)
        return false;

    *output_len = 0;

    // Calculate required buffer size first.
    size_t required = 2;  // Two END markers

    for (size_t i = 0; i < input_len; i++) {
        size_t extra = (input[i] == SLIP_END ||
                        input[i] == SLIP_ESC) ? 2 : 1;

        if (required > SIZE_MAX - extra)
            return false;

        required += extra;
    }

    if (output_capacity < required)
        return false;

    size_t pos = 0;

    output[pos++] = SLIP_END;

    for (size_t i = 0; i < input_len; i++) {

        if (input[i] == SLIP_END) {
            output[pos++] = SLIP_ESC;
            output[pos++] = SLIP_ESC_END;
        }
        else if (input[i] == SLIP_ESC) {
            output[pos++] = SLIP_ESC;
            output[pos++] = SLIP_ESC_ESC;
        }
        else {
            output[pos++] = input[i];
        }
    }

    output[pos++] = SLIP_END;

    *output_len = pos;
    return true;
}


bool slip_decode(
    const uint8_t *input,
    size_t input_len,
    uint8_t *output,
    size_t output_capacity,
    size_t *output_len)
{
    if (output_len != NULL) {
        *output_len = 0;
    }

    if (!input || !output || !output_len || input_len < 2) {
        return false;
    }

    // Validate frame boundaries
    if (input[0] != SLIP_END ||
        input[input_len - 1] != SLIP_END) {
        return false;
    }

    size_t pos = 0;

    for (size_t i = 1; i < input_len - 1; i++) {
        uint8_t byte = input[i];

        // Handle escaped bytes
        if (byte == SLIP_ESC) {
            if (i + 1 >= input_len - 1) {
                return false;
            }

            uint8_t escaped = input[++i];

            if (escaped == SLIP_ESC_END) {
                byte = SLIP_END;
            }
            else if (escaped == SLIP_ESC_ESC) {
                byte = SLIP_ESC;
            }
            else {
                return false;
            }
        }
        else if (byte == SLIP_END) {
            return false;
        }

        // Prevent buffer overflow
        if (pos >= output_capacity) {
            return false;
        }

        output[pos++] = byte;
    }

    *output_len = pos;
    return true;
}
