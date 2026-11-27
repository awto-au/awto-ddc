enum Small { A, B, C };
enum Big { X = 300 };
enum Small s;
enum Big b;
char sz_small = sizeof(enum Small);
char sz_big = sizeof(enum Big);
char sz_var = sizeof(s);
