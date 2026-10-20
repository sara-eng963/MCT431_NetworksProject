
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "slip.h"

int main(void)
{
    // Test 1: Verify SLIP framing and escaping
    const uint8_t input[] = {
        0x01, 0xC0, 0xDB, 0x02
    };

    const uint8_t expected[] = {
        0xC0,                   // Start
        0x01,
        0xDB, 0xDC,             // Escaped 0xC0
        0xDB, 0xDD,             // Escaped 0xDB
        0x02,
        0xC0                    // End
    };

    uint8_t output[sizeof(expected)] = {0};
    size_t output_len = 0;

    assert(slip_encode(
        input, sizeof(input),
        output, sizeof(output),
        &output_len
    ));

    assert(output_len == sizeof(expected));
    assert(memcmp(output, expected, sizeof(expected)) == 0);

    printf("PASS: SLIP framing and escaping\n");

    // Test 2: Insufficient output buffer
    output_len = 99;

    assert(!slip_encode(
        input, sizeof(input),
        output, sizeof(output) - 1,
        &output_len
    ));

    assert(output_len == 0);

    printf("PASS: Buffer capacity validation\n");

    return 0;
}
