
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "atr.h"

int main(void)
{
    // Known input: 16-byte payload
    uint8_t payload[16];

    for (size_t i = 0; i < sizeof(payload); i++) {
        payload[i] = (uint8_t)i;
    }

    // Independently calculated expected ATR bytes
    const uint8_t expected[] = {
        0x12, 0x34,                   // test_id
        0x00, 0x00, 0x00, 0x00,       // seq
        0x00, 0x10,                   // payload_len
        0x00, 0x01, 0x02, 0x03,
        0x04, 0x05, 0x06, 0x07,
        0x08, 0x09, 0x0A, 0x0B,
        0x0C, 0x0D, 0x0E, 0x0F,       // payload
        0x5A, 0x74                    // CRC-16
    };

    uint8_t output[sizeof(expected)];
    size_t output_len = 0;

    // Test 1: Correct encoding
    assert(atr_encode(
        0x1234, 0,
        payload, sizeof(payload),
        output, sizeof(output),
        &output_len
    ));

    assert(output_len == sizeof(expected));
    assert(memcmp(output, expected, sizeof(expected)) == 0);

    printf("PASS: ATR encoding and byte order\n");

    // Test 2: Insufficient buffer
    output_len = 99;

    assert(!atr_encode(
        0x1234, 0,
        payload, sizeof(payload),
        output, sizeof(output) - 1,
        &output_len
    ));

    assert(output_len == 0);

    printf("PASS: Buffer capacity validation\n");

    return 0;
}
