
#include <assert.h>
#include <stdint.h>
#include <stdio.h>

#include "atr.h"

int main(void)
{
    const uint8_t data[] = "123456789";

    uint16_t crc = atr_crc16(data, sizeof(data) - 1);

    assert(crc == 0x29B1);

    printf("PASS: CRC-16/CCITT-FALSE\n");
    return 0;
}
