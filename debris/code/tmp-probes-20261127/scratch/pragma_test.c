extern unsigned char g_a[64], g_b[64];

#pragma opt_code_size
void CopySize(void)
{
    unsigned char i;
    for(i = 0; i < 64; i++) { g_a[i] = g_b[i] + 3; }
}

#pragma opt_code_speed
void CopySpeed(void)
{
    unsigned char i;
    for(i = 0; i < 64; i++) { g_a[i] = g_b[i] + 3; }
}
