
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "slip.h"

int main(void)
{
    const uint8_t encoded[] = {
        0xC0, 0x01, 0xDB, 0xDC,
        0xDB, 0xDD, 0x02, 0xC0
    };

    const uint8_t expected[] = {
        0x01, 0xC0, 0xDB, 0x02
    };

    uint8_t output[sizeof(expected)];
    size_t output_len = 0;

    // Test 1: Valid frame
    assert(slip_decode(
        encoded, sizeof(encoded),
        output, sizeof(output),
        &output_len
    ));

    assert(output_len == sizeof(expected));
    assert(memcmp(output, expected, sizeof(expected)) == 0);

    printf("PASS: SLIP decoding\n");

    // Test 2: Insufficient output capacity
    assert(!slip_decode(
        encoded, sizeof(encoded),
        output, sizeof(output) - 1,
        &output_len
    ));

    assert(output_len == 0);

    printf("PASS: Buffer overflow protection\n");

    // Test 3: Invalid escape sequence
    const uint8_t invalid_escape[] = {
        0xC0, 0x01, 0xDB, 0xAA, 0xC0
    };

    assert(!slip_decode(
        invalid_escape, sizeof(invalid_escape),
        output, sizeof(output),
        &output_len
    ));

    printf("PASS: Invalid escape rejected\n");

    // Test 4: Missing END delimiter
    const uint8_t invalid_frame[] = {
        0xC0, 0x01, 0x02, 0x03
    };

    assert(!slip_decode(
        invalid_frame, sizeof(invalid_frame),
        output, sizeof(output),
        &output_len
    ));

    printf("PASS: Missing delimiter rejected\n");

    return 0;
}
