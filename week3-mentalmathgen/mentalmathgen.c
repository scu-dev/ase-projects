#define _CRT_SECURE_NO_WARNINGS
#include <errno.h>
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

/* Exact arithmetic: each normalized numerator/denominator is at most LIMIT.
 * Products and sums of two such fractions fit in int64_t. */
#define LIMIT INT64_C(1000000000)
#define MAX_NUMBERS 16
#define TEXT_SIZE 512

typedef struct { int64_t n, d; } Fraction;
typedef struct {
    int count, numbers, mul_div, brackets, min, max;
    int negative, remainder, fractions, spacing, answers;
    uint32_t seed;
} Config;
typedef struct { char symbol; int precedence; } Operator;
static const Operator operators[] = {{'+', 1}, {'-', 1}, {'*', 2}, {'/', 2}};
typedef struct { int left, right, op, number; Fraction value; } Node;
typedef struct { Node nodes[2 * MAX_NUMBERS - 1]; int used; } Expression;
typedef struct { char text[TEXT_SIZE]; Fraction value; int remainder, divisor; } Question;

static uint32_t random_state;
static uint32_t next_random(void)
{
    uint32_t x = random_state;
    x ^= x << 13;
    x ^= x >> 17;
    x ^= x << 5;
    return random_state = x;
}

static int choose(int bound)
{
    return (int)(next_random() % (uint32_t)bound);
}

static int64_t gcd(int64_t a, int64_t b)
{
    while (b) { int64_t t = a % b; a = b; b = t; }
    return a;
}

static int normalize(Fraction *v)
{
    int64_t g;
    if (!v->d) return 0;
    if (v->d < 0) { v->n = -v->n; v->d = -v->d; }
    g = gcd(v->n < 0 ? -v->n : v->n, v->d);
    v->n /= g;
    v->d /= g;
    return v->n >= -LIMIT && v->n <= LIMIT && v->d <= LIMIT;
}

static int calculate(Fraction a, Fraction b, int op, const Config *c, Fraction *v)
{
    switch (operators[op].symbol) {
    case '+': v->n = a.n * b.d + b.n * a.d; v->d = a.d * b.d; break;
    case '-': v->n = a.n * b.d - b.n * a.d; v->d = a.d * b.d; break;
    case '*': v->n = a.n * b.n; v->d = a.d * b.d; break;
    case '/':
        if (!b.n) return 0;
        v->n = a.n * b.d; v->d = a.d * b.n;
        break;
    default: return 0;
    }
    if (!normalize(v) || (!c->negative && v->n < 0)) return 0;
    if (operators[op].symbol == '/' && v->d != 1 &&
        !(c->numbers == 2 ? c->remainder : c->fractions)) return 0;
    return 1;
}

static int leaf(Expression *e, const Config *c)
{
    int id = e->used++;
    Node *n = &e->nodes[id];
    n->op = -1;
    n->number = c->min + choose(c->max - c->min + 1);
    n->value.n = n->number;
    n->value.d = 1;
    return id;
}

static int combine(Expression *e, int left, int right, int op, const Config *c)
{
    int id;
    Node *n;
    if (left < 0 || right < 0) return -1;
    id = e->used++;
    n = &e->nodes[id];
    n->left = left; n->right = right; n->op = op;
    if (!calculate(e->nodes[left].value, e->nodes[right].value, op, c, &n->value))
        return -1;
    return id;
}

/* Parenthesized expressions can have any binary-tree shape. */
static int tree(Expression *e, int numbers, const Config *c)
{
    int split, left, right, op;
    if (numbers == 1) return leaf(e, c);
    split = 1 + choose(numbers - 1);
    left = tree(e, split, c);
    if (left < 0) return -1;
    right = tree(e, numbers - split, c);
    op = choose(c->mul_div ? 4 : 2);
    return combine(e, left, right, op, c);
}

/* Operator/value stacks retain ordinary precedence and left associativity. */
static int flat(Expression *e, const Config *c)
{
    int values[MAX_NUMBERS], ops[MAX_NUMBERS], nv = 0, no = 0, i;
    values[nv++] = leaf(e, c);
    for (i = 1; i < c->numbers; ++i) {
        int op = choose(c->mul_div ? 4 : 2);
        while (no && operators[ops[no - 1]].precedence >= operators[op].precedence) {
            int right = values[--nv], left = values[--nv];
            int result = combine(e, left, right, ops[--no], c);
            if (result < 0) return -1;
            values[nv++] = result;
        }
        ops[no++] = op;
        values[nv++] = leaf(e, c);
    }
    while (no) {
        int right = values[--nv], left = values[--nv];
        int result = combine(e, left, right, ops[--no], c);
        if (result < 0) return -1;
        values[nv++] = result;
    }
    return values[0];
}

static void render(const Expression *e, int id, int brackets, int root, char *out, size_t *pos)
{
    const Node *n = &e->nodes[id];
    if (n->op < 0) {
        /* Negative operands are grouped even in otherwise flat expressions. */
        *pos += (size_t)sprintf(out + *pos, n->number < 0 ? "(%d)" : "%d", n->number);
        return;
    }
    if (brackets && !root) out[(*pos)++] = '(';
    render(e, n->left, brackets, 0, out, pos);
    *pos += (size_t)sprintf(out + *pos, " %c ", operators[n->op].symbol);
    render(e, n->right, brackets, 0, out, pos);
    if (brackets && !root) out[(*pos)++] = ')';
    out[*pos] = '\0';
}

static int generate(const Config *c, Question *q)
{
    Expression e = {0};
    int root = c->brackets && c->numbers > 2 ? tree(&e, c->numbers, c) : flat(&e, c);
    size_t pos = 0;
    if (root < 0) return 0;
    render(&e, root, c->brackets && c->numbers > 2, 1, q->text, &pos);
    q->value = e.nodes[root].value;
    q->remainder = 0;
    if (c->numbers == 2 && e.nodes[root].op == 3 && c->remainder) {
        int a = e.nodes[e.nodes[root].left].number;
        int b = e.nodes[e.nodes[root].right].number;
        q->value.n = a / b; q->value.d = 1;
        q->remainder = a % b; q->divisor = b;
    }
    return 1;
}

static uint32_t hash(const char *s)
{
    uint32_t h = UINT32_C(2166136261);
    while (*s) { h ^= (unsigned char)*s++; h *= UINT32_C(16777619); }
    return h;
}

static void usage(void)
{
    puts("Usage: mentalmathgen [options]\n"
         "  --count N        Question count (1..10000; default 20)\n"
         "  --numbers N      Operands per question (2..16; default 2)\n"
         "  --mul-div 0|1    Enable multiplication/division (default 0)\n"
         "  --brackets 0|1   Enable parentheses for >2 operands (default 0)\n"
         "  --min N          Smallest operand (0..1000000; default 0)\n"
         "  --max N          Largest operand (0..1000000; default 20)\n"
         "  --negative 0|1   Allow negative intermediate results (default 0)\n"
         "  --remainder 0|1  Allow division remainder with 2 operands (default 0)\n"
         "  --fractions 0|1  Allow fractional division with >2 operands (default 0)\n"
         "  --spacing N      Blank lines between questions (0..100; default 0)\n"
         "  --answers 0|1    Print a separate answer section (default 0)\n"
         "  --seed N         Reproducible random seed (1..2147483647)\n"
         "  --help           Show this help");
}

static int parse(int argc, char **argv, Config *c)
{
    int i;
    for (i = 1; i < argc; ++i) {
        int *target = NULL, low = 0, high = 1;
        long value;
        char *end;
        const char *name = argv[i];
        if (!strcmp(name, "--help")) { usage(); return 2; }
        if (!strcmp(name, "--count")) { target = &c->count; low = 1; high = 10000; }
        else if (!strcmp(name, "--numbers")) { target = &c->numbers; low = 2; high = MAX_NUMBERS; }
        else if (!strcmp(name, "--min")) { target = &c->min; high = 1000000; }
        else if (!strcmp(name, "--max")) { target = &c->max; high = 1000000; }
        else if (!strcmp(name, "--mul-div")) target = &c->mul_div;
        else if (!strcmp(name, "--brackets")) target = &c->brackets;
        else if (!strcmp(name, "--negative")) target = &c->negative;
        else if (!strcmp(name, "--remainder")) target = &c->remainder;
        else if (!strcmp(name, "--fractions")) target = &c->fractions;
        else if (!strcmp(name, "--answers")) target = &c->answers;
        else if (!strcmp(name, "--spacing")) { target = &c->spacing; high = 100; }
        else if (!strcmp(name, "--seed")) { low = 1; high = 2147483647; }
        else { fprintf(stderr, "Unknown option: %s\n", name); return 0; }
        if (++i == argc) { fprintf(stderr, "Missing value for %s\n", name); return 0; }
        errno = 0;
        value = strtol(argv[i], &end, 10);
        if (errno || end == argv[i] || *end || value < low || value > high) {
            fprintf(stderr, "Invalid value for %s: expected %d..%d\n", name, low, high);
            return 0;
        }
        if (target) *target = (int)value;
        else c->seed = (uint32_t)value;
    }
    if (c->min > c->max) { fputs("--min must not exceed --max.\n", stderr); return 0; }
    return 1;
}

int main(int argc, char **argv)
{
    Config c = {20, 2, 0, 0, 0, 20, 0, 0, 0, 0, 0, 0};
    Question *questions;
    int *slots;
    size_t capacity = 1, attempts = 0, budget;
    int count = 0, i, parsed = parse(argc, argv, &c);
    if (parsed != 1) return parsed == 2 ? 0 : 2;
    random_state = c.seed ? c.seed : (uint32_t)time(NULL);
    if (!random_state) random_state = 1;
    while (capacity < (size_t)c.count * 2) capacity *= 2;
    questions = (Question *)calloc((size_t)c.count, sizeof(*questions));
    slots = (int *)calloc(capacity, sizeof(*slots));
    if (!questions || !slots) {
        fputs("Out of memory.\n", stderr); free(questions); free(slots); return 1;
    }
    budget = (size_t)c.count * 2000 + 10000;
    while (count < c.count && attempts++ < budget) {
        Question candidate = {0};
        size_t slot;
        if (!generate(&c, &candidate)) continue;
        slot = (size_t)hash(candidate.text) & (capacity - 1);
        while (slots[slot] && strcmp(questions[slots[slot] - 1].text, candidate.text))
            slot = (slot + 1) & (capacity - 1);
        if (slots[slot]) continue;
        questions[count] = candidate;
        slots[slot] = ++count;
    }
    if (count != c.count) {
        fprintf(stderr, "Could generate only %d of %d unique questions within the attempt limit. "
                "Widen the range, relax constraints, or reduce --count.\n", count, c.count);
        free(questions); free(slots); return 1;
    }
    for (i = 0; i < count; ++i) {
        int line;
        printf("%d. %s = ________\n", i + 1, questions[i].text);
        if (i + 1 < count) for (line = 0; line < c.spacing; ++line) putchar('\n');
    }
    if (c.answers) {
        puts("\nAnswers:");
        for (i = 0; i < count; ++i) {
            Question *q = &questions[i];
            printf("%d. %" PRId64, i + 1, q->value.n);
            if (q->value.d != 1) printf("/%" PRId64, q->value.d);
            if (q->remainder) printf("...%d", q->remainder);
            putchar('\n');
        }
    }
    free(questions); free(slots);
    return fflush(stdout) == EOF ? 1 : 0;
}