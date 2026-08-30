#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <unistd.h>

/*
 * Reviewed native launcher template for the sealed R8 UE 5.7 executor.
 *
 * Production compilation MUST define every REVIEWED_* macro below, use the
 * compiler/flags pinned by the external audit plan, and compare the resulting
 * static ELF byte-for-byte with the independently reviewed binary pin.  The
 * checked-in template intentionally does not compile into production authority
 * without those literals.
 */
#ifndef REVIEWED_LOADER_PATH
#error "REVIEWED_LOADER_PATH is required"
#endif
#ifndef REVIEWED_LOADER_SHA256
#error "REVIEWED_LOADER_SHA256 is required"
#endif
#ifndef REVIEWED_LOADER_BYTES
#error "REVIEWED_LOADER_BYTES is required"
#endif
#ifndef REVIEWED_PYTHON_PATH
#error "REVIEWED_PYTHON_PATH is required"
#endif
#ifndef REVIEWED_PYTHON_SHA256
#error "REVIEWED_PYTHON_SHA256 is required"
#endif
#ifndef REVIEWED_PYTHON_BYTES
#error "REVIEWED_PYTHON_BYTES is required"
#endif
#ifndef REVIEWED_LIBRARY_PATH
#error "REVIEWED_LIBRARY_PATH is required"
#endif
#ifndef REVIEWED_ATTEMPT_NAME
#error "REVIEWED_ATTEMPT_NAME is required"
#endif

#define EXECUTOR_PATH \
  "/root/vista-r8-ue57-executor-r2/bundle/" \
  "makehuman_cc0_animation_runtime_executor.py"
#define EXECUTION_ACK \
  "I acknowledge this isolated CC0 R8 animation-only UE 5.7 import remains " \
  "unaccepted until runtime, two-client, and human-motion review gates pass"

typedef struct {
  uint32_t state[8];
  uint64_t bit_count;
  unsigned char block[64];
  size_t block_bytes;
} sha256_ctx;

static const uint32_t k[64] = {
  0x428a2f98u,0x71374491u,0xb5c0fbcfu,0xe9b5dba5u,0x3956c25bu,0x59f111f1u,0x923f82a4u,0xab1c5ed5u,
  0xd807aa98u,0x12835b01u,0x243185beu,0x550c7dc3u,0x72be5d74u,0x80deb1feu,0x9bdc06a7u,0xc19bf174u,
  0xe49b69c1u,0xefbe4786u,0x0fc19dc6u,0x240ca1ccu,0x2de92c6fu,0x4a7484aau,0x5cb0a9dcu,0x76f988dau,
  0x983e5152u,0xa831c66du,0xb00327c8u,0xbf597fc7u,0xc6e00bf3u,0xd5a79147u,0x06ca6351u,0x14292967u,
  0x27b70a85u,0x2e1b2138u,0x4d2c6dfcu,0x53380d13u,0x650a7354u,0x766a0abbu,0x81c2c92eu,0x92722c85u,
  0xa2bfe8a1u,0xa81a664bu,0xc24b8b70u,0xc76c51a3u,0xd192e819u,0xd6990624u,0xf40e3585u,0x106aa070u,
  0x19a4c116u,0x1e376c08u,0x2748774cu,0x34b0bcb5u,0x391c0cb3u,0x4ed8aa4au,0x5b9cca4fu,0x682e6ff3u,
  0x748f82eeu,0x78a5636fu,0x84c87814u,0x8cc70208u,0x90befffau,0xa4506cebu,0xbef9a3f7u,0xc67178f2u
};

static uint32_t rotr(uint32_t x, unsigned n) { return (x >> n) | (x << (32u - n)); }

static void sha_transform(sha256_ctx *c, const unsigned char *p) {
  uint32_t w[64], a,b,d,e,f,g,h,t1,t2,cc;
  for (int i=0;i<16;i++) w[i]=((uint32_t)p[4*i]<<24)|((uint32_t)p[4*i+1]<<16)|((uint32_t)p[4*i+2]<<8)|p[4*i+3];
  for (int i=16;i<64;i++) {
    uint32_t s0=rotr(w[i-15],7)^rotr(w[i-15],18)^(w[i-15]>>3);
    uint32_t s1=rotr(w[i-2],17)^rotr(w[i-2],19)^(w[i-2]>>10);
    w[i]=w[i-16]+s0+w[i-7]+s1;
  }
  a=c->state[0]; b=c->state[1]; cc=c->state[2]; d=c->state[3];
  e=c->state[4]; f=c->state[5]; g=c->state[6]; h=c->state[7];
  for (int i=0;i<64;i++) {
    uint32_t s1=rotr(e,6)^rotr(e,11)^rotr(e,25);
    uint32_t ch=(e&f)^((~e)&g);
    t1=h+s1+ch+k[i]+w[i];
    uint32_t s0=rotr(a,2)^rotr(a,13)^rotr(a,22);
    uint32_t maj=(a&b)^(a&cc)^(b&cc);
    t2=s0+maj; h=g; g=f; f=e; e=d+t1; d=cc; cc=b; b=a; a=t1+t2;
  }
  c->state[0]+=a;c->state[1]+=b;c->state[2]+=cc;c->state[3]+=d;
  c->state[4]+=e;c->state[5]+=f;c->state[6]+=g;c->state[7]+=h;
}

static void sha_init(sha256_ctx *c) {
  static const uint32_t initial[8]={0x6a09e667u,0xbb67ae85u,0x3c6ef372u,0xa54ff53au,0x510e527fu,0x9b05688cu,0x1f83d9abu,0x5be0cd19u};
  memcpy(c->state,initial,sizeof(initial)); c->bit_count=0; c->block_bytes=0;
}

static void sha_update(sha256_ctx *c, const unsigned char *p, size_t n) {
  c->bit_count += (uint64_t)n*8u;
  while (n) {
    size_t take=64-c->block_bytes; if (take>n) take=n;
    memcpy(c->block+c->block_bytes,p,take); c->block_bytes+=take; p+=take; n-=take;
    if (c->block_bytes==64) { sha_transform(c,c->block); c->block_bytes=0; }
  }
}

static void sha_final(sha256_ctx *c, unsigned char out[32]) {
  uint64_t bits=c->bit_count; unsigned char one=0x80,zero=0;
  sha_update(c,&one,1); while(c->block_bytes!=56) sha_update(c,&zero,1);
  unsigned char length[8]; for(int i=0;i<8;i++) length[7-i]=(unsigned char)(bits>>(8*i));
  /* sha_update changes bit_count, which is irrelevant after this block. */
  sha_update(c,length,8);
  for(int i=0;i<8;i++) for(int j=0;j<4;j++) out[4*i+j]=(unsigned char)(c->state[i]>>(24-8*j));
}

static int fail(const char *message) {
  (void)!write(STDERR_FILENO,message,strlen(message));
  (void)!write(STDERR_FILENO,"\n",1);
  return 126;
}

static int hex_equal(const unsigned char digest[32], const char *expected) {
  static const char hex[]="0123456789abcdef"; char actual[65];
  for(int i=0;i<32;i++){actual[2*i]=hex[digest[i]>>4];actual[2*i+1]=hex[digest[i]&15];}
  actual[64]='\0'; return strlen(expected)==64 && memcmp(actual,expected,64)==0;
}

static int open_verified(const char *path, off_t bytes, const char *sha, int keep_exec) {
  int flags=O_RDONLY|O_NOFOLLOW|O_CLOEXEC; int fd=open(path,flags);
  if(fd<0) return -1;
  struct stat st; if(fstat(fd,&st)||!S_ISREG(st.st_mode)||st.st_nlink!=1||st.st_uid!=0||st.st_gid!=0||(st.st_mode&07777)!=0555||st.st_size!=bytes){close(fd);return -1;}
  sha256_ctx ctx; sha_init(&ctx); unsigned char buffer[1024*1024],digest[32]; ssize_t n;
  while((n=read(fd,buffer,sizeof(buffer)))>0) sha_update(&ctx,buffer,(size_t)n);
  if(n<0){close(fd);return -1;} sha_final(&ctx,digest);
  if(!hex_equal(digest,sha)||lseek(fd,0,SEEK_SET)<0){close(fd);return -1;}
  if(keep_exec && fcntl(fd,F_SETFD,0)<0){close(fd);return -1;}
  return fd;
}

int main(int argc, char **argv) {
  if(argc!=2||geteuid()!=0) return fail("R8_LAUNCHER: exactly one operation and root EUID required");
  int audit=strcmp(argv[1],"--audit-authorities")==0;
  int execute=strcmp(argv[1],"--execute")==0;
  int reconcile=strcmp(argv[1],"--reconcile-durability")==0;
  if(!audit&&!execute&&!reconcile) return fail("R8_LAUNCHER: operation differs");
  int loader=open_verified(REVIEWED_LOADER_PATH,(off_t)REVIEWED_LOADER_BYTES,REVIEWED_LOADER_SHA256,0);
  int python=open_verified(REVIEWED_PYTHON_PATH,(off_t)REVIEWED_PYTHON_BYTES,REVIEWED_PYTHON_SHA256,1);
  if(loader<0||python<0) return fail("R8_LAUNCHER: immutable loader/Python pin differs");
  char python_fd[64]; if(snprintf(python_fd,sizeof(python_fd),"/proc/self/fd/%d",python)<0) return fail("R8_LAUNCHER: fd path failed");
  char *audit_argv[]={"ld-linux", "--argv0", REVIEWED_PYTHON_PATH,
    "--library-path", REVIEWED_LIBRARY_PATH, python_fd, "-I", "-B", EXECUTOR_PATH,
    "--attempt-name", REVIEWED_ATTEMPT_NAME, "--audit-authorities", NULL};
  char *execute_argv[]={"ld-linux", "--argv0", REVIEWED_PYTHON_PATH,
    "--library-path", REVIEWED_LIBRARY_PATH, python_fd, "-I", "-B", EXECUTOR_PATH,
    "--attempt-name", REVIEWED_ATTEMPT_NAME,
    "--execute", "--execution-acknowledgement", EXECUTION_ACK, NULL};
  char *reconcile_argv[]={"ld-linux", "--argv0", REVIEWED_PYTHON_PATH,
    "--library-path", REVIEWED_LIBRARY_PATH, python_fd, "-I", "-B", EXECUTOR_PATH,
    "--attempt-name", REVIEWED_ATTEMPT_NAME, "--reconcile-durability", NULL};
  char *const child_env[]={"PATH=/usr/bin:/bin","HOME=/nonexistent","LANG=C.UTF-8",
    "PYTHONNOUSERSITE=1","PYTHONDONTWRITEBYTECODE=1",NULL};
  char **child_argv=audit?audit_argv:(execute?execute_argv:reconcile_argv);
  syscall(SYS_execveat,loader,"",child_argv,child_env,AT_EMPTY_PATH);
  return fail("R8_LAUNCHER: execveat failed");
}
