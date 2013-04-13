#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include "primegen.h" 
/*inline void set_bit(char *byteField, unsigned long long num) {
    byteField[num >> 3] |= (1 << (num & 0xf));
}
inline void clear_bit(char *byteField, unsigned long long num) {
    byteField[num >> 3] &= (~(1 << (num & 0xf)));
}

inline int isBit(char *byteField, unsigned long long num) {
    return byteField[num >> 3] & (1 << (num & 0xf)); 
}*/

void find_primes(uint64_t limit) {
    primegen pg;
    uint64_t prime = 0;
    primegen_init(&pg);
    while( prime < limit) {
        prime = primegen_next(&pg);
        printf("%lld %d\n", (int64_t)prime, __builtin_popcountll(prime - 1));
    }
}

int main(int argc, char** argv) {
    if (argc < 2) {
        printf("Bad programmer\n");
        return 1;
    }
    find_primes(strtoull(argv[1], NULL, 10));
    return 1;
}
