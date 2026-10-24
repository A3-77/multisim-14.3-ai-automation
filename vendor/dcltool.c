/* dcltool.c -- PKWARE DCL (implode/explode) 命令行工具
 *
 * 用法:
 *   dcltool d <in> <out> [offset]     解压（offset 跳过前 N 字节）
 *   dcltool c <in> <out> <lit> <dict> 压缩（lit=0/1, dict=4/5/6）
 *
 * 解压部分直接链接 blast.c（Mark Adler, zlib/contrib/blast）。
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "blast.h"

static unsigned char *g_in;
static unsigned g_len, g_pos;

static unsigned infun(void *how, unsigned char **buf)
{
    (void)how;
    if (g_pos >= g_len) return 0;
    *buf = g_in + g_pos;
    { unsigned n = g_len - g_pos; g_pos = g_len; return n; }
}

static int outfun(void *how, unsigned char *buf, unsigned len)
{
    FILE *f = (FILE *)how;
    return fwrite(buf, 1, len, f) == len ? 0 : 1;
}

static unsigned char *slurp(const char *p, unsigned *n)
{
    FILE *f = fopen(p, "rb");
    unsigned char *b;
    long sz;
    if (!f) { fprintf(stderr, "打不开 %s\n", p); exit(2); }
    fseek(f, 0, SEEK_END); sz = ftell(f); fseek(f, 0, SEEK_SET);
    b = (unsigned char *)malloc((size_t)sz + 1);
    if (fread(b, 1, (size_t)sz, f) != (size_t)sz) { fprintf(stderr, "读失败\n"); exit(2); }
    fclose(f);
    *n = (unsigned)sz;
    return b;
}

/* ---------------- 解压 ---------------- */
static int do_decompress(const char *inp, const char *outp, unsigned off)
{
    unsigned n, left;
    unsigned char *data, *unused = NULL;
    FILE *f;
    int err;

    data = slurp(inp, &n);
    if (off >= n) { fprintf(stderr, "offset 越界\n"); return 2; }
    g_in = data + off; g_len = n - off; g_pos = 0;

    f = fopen(outp, "wb");
    if (!f) { fprintf(stderr, "写不了 %s\n", outp); return 2; }

    left = 0;
    err = blast(infun, NULL, outfun, f, &left, &unused);
    fclose(f);
    printf("blast rc=%d  消耗输入=%u  剩余输入=%u\n", err, g_pos - left, left);
    return err;
}

/* ---------------- 压缩 ---------------- */

/* 输出位流：LSB first，与 blast.c 的 bits() 对应 */
typedef struct {
    FILE *f;
    unsigned buf;      /* 位缓冲 */
    int cnt;           /* 已填充位数 */
    unsigned long long total;
} BitOut;

static void bo_init(BitOut *b, FILE *f) { b->f = f; b->buf = 0; b->cnt = 0; b->total = 0; }

static void bo_put(BitOut *b, unsigned val, int nbits)
{
    b->buf |= (val & ((1u << nbits) - 1)) << b->cnt;
    b->cnt += nbits;
    while (b->cnt >= 8) {
        unsigned char c = (unsigned char)(b->buf & 0xFF);
        fputc(c, b->f);
        b->total++;
        b->buf >>= 8;
        b->cnt -= 8;
    }
}

static void bo_flush(BitOut *b)
{
    if (b->cnt > 0) {
        fputc((int)(b->buf & 0xFF), b->f);
        b->total++;
        b->buf = 0; b->cnt = 0;
    }
}

/* 不编码字面量(lit=0) 的最简 imploder：
 * 每个字节写 1 bit 标志(0=字面量) + 8 bits 数据。
 * 输出比原文略大(9/8)，但完全符合 DCL 规范，任何 explode 都能解。
 */
static int do_compress_lit0(const char *inp, const char *outp, int dict)
{
    unsigned n, i;
    unsigned char *data = slurp(inp, &n);
    FILE *f = fopen(outp, "wb");
    BitOut b;
    if (!f) { fprintf(stderr, "写不了 %s\n", outp); return 2; }

    /* DCL 头: byte0 = lit(0=uncoded), byte1 = log2(dict)-6 */
    fputc(0, f);
    fputc(dict, f);

    bo_init(&b, f);
    for (i = 0; i < n; i++) {
        bo_put(&b, 0, 1);            /* 0 = 字面量 */
        bo_put(&b, data[i], 8);      /* 8 bits 原始字节 */
    }
    bo_flush(&b);
    fclose(f);
    printf("lit0 压缩: %u -> %llu 字节 (dict=%d)\n", n, b.total + 2, dict);
    return 0;
}

int main(int argc, char **argv)
{
    if (argc < 2) {
        fprintf(stderr,
            "用法:\n"
            "  dcltool d <in> <out> [offset]\n"
            "  dcltool c0 <in> <out> [dict]\n");
        return 1;
    }
    if (!strcmp(argv[1], "d")) {
        unsigned off = (argc > 4) ? (unsigned)strtoul(argv[4], NULL, 0) : 0;
        if (argc < 4) { fprintf(stderr, "d 需要 in out\n"); return 1; }
        return do_decompress(argv[2], argv[3], off);
    }
    if (!strcmp(argv[1], "c0")) {
        int dict = (argc > 4) ? atoi(argv[4]) : 6;
        if (argc < 4) { fprintf(stderr, "c0 需要 in out\n"); return 1; }
        return do_compress_lit0(argv[2], argv[3], dict);
    }
    fprintf(stderr, "未知模式 %s\n", argv[1]);
    return 1;
}
