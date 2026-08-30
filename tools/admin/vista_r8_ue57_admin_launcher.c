#define _GNU_SOURCE

#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <unistd.h>

/*
 * Closed native entry point for the two sequential R8 administrator stages.
 *
 * Build exactly one variant with a stage selector and four externally reviewed
 * Python/helper byte-pin macros.  Paths, operations, and acknowledgements are
 * compiled literals; no runtime caller can supply a path, pin, or free-form
 * acknowledgement.
 */
#if (defined(VISTA_R8_ADMIN_STAGE_RUNTIME) +                            \
     defined(VISTA_R8_ADMIN_STAGE_BUNDLE)) != 1
#error "define exactly one VISTA R8 administrator stage"
#endif
#ifndef EXPECTED_PYTHON_SHA256
#error "EXPECTED_PYTHON_SHA256 is required"
#endif
#ifndef EXPECTED_PYTHON_SIZE
#error "EXPECTED_PYTHON_SIZE is required"
#endif
#ifndef EXPECTED_HELPER_SHA256
#error "EXPECTED_HELPER_SHA256 is required"
#endif
#ifndef EXPECTED_HELPER_SIZE
#error "EXPECTED_HELPER_SIZE is required"
#endif

_Static_assert(EXPECTED_PYTHON_SIZE > 0, "EXPECTED_PYTHON_SIZE must be positive");
_Static_assert(EXPECTED_HELPER_SIZE > 0, "EXPECTED_HELPER_SIZE must be positive");
_Static_assert(sizeof(EXPECTED_PYTHON_SHA256) == 65,
               "EXPECTED_PYTHON_SHA256 must contain 64 hexadecimal bytes");
_Static_assert(sizeof(EXPECTED_HELPER_SHA256) == 65,
               "EXPECTED_HELPER_SHA256 must contain 64 hexadecimal bytes");

#define PYTHON_PATH "/usr/bin/python3.10"
#define CORE_HELPER_PATH                                                     \
  "/root/vista-r8-ue57-authority-r2/vista_r8_ue57_authority_admin.py"

#if defined(VISTA_R8_ADMIN_STAGE_RUNTIME)
#define EXPECTED_SELF_PATH                                                   \
  "/root/vista-r8-ue57-runtime-plan-r1/publish-reconcile-r8-ue57"
#define PUBLISH_OPERATION "publish-host-runtime"
#define RECONCILE_OPERATION "reconcile-host-runtime"
#define PUBLISH_ACKNOWLEDGEMENT                                              \
  "I acknowledge one fresh publication of the reviewed VISTA R8 UE 5.7 "   \
  "host-runtime authority."
#define RECONCILE_ACKNOWLEDGEMENT                                            \
  "I acknowledge reconciliation of the existing reviewed VISTA R8 UE 5.7 " \
  "host-runtime authority without republishing or deleting it."
#else
#define EXPECTED_SELF_PATH                                                   \
  "/root/vista-r8-ue57-bundle-plan-r1/publish-reconcile-r8-ue57"
#define PUBLISH_OPERATION "publish-executor-bundle"
#define RECONCILE_OPERATION "reconcile-executor-bundle"
#define PUBLISH_ACKNOWLEDGEMENT                                              \
  "I acknowledge one fresh publication of the reviewed VISTA R8 UE 5.7 R2 " \
  "executor bundle."
#define RECONCILE_ACKNOWLEDGEMENT                                            \
  "I acknowledge reconciliation of the existing reviewed VISTA R8 UE 5.7 " \
  "R2 executor bundle without republishing or deleting it."
#endif

enum {
  SELF_MODE = 0555,
  PYTHON_MODE = 0755,
  CORE_HELPER_MODE = 0500,
  FAILURE_EXIT = 126,
};

typedef struct {
  uint32_t state[8];
  uint64_t bit_count;
  unsigned char block[64];
  size_t block_bytes;
} sha256_context;

static const uint32_t sha256_round_constants[64] = {
    0x428a2f98u, 0x71374491u, 0xb5c0fbcfu, 0xe9b5dba5u,
    0x3956c25bu, 0x59f111f1u, 0x923f82a4u, 0xab1c5ed5u,
    0xd807aa98u, 0x12835b01u, 0x243185beu, 0x550c7dc3u,
    0x72be5d74u, 0x80deb1feu, 0x9bdc06a7u, 0xc19bf174u,
    0xe49b69c1u, 0xefbe4786u, 0x0fc19dc6u, 0x240ca1ccu,
    0x2de92c6fu, 0x4a7484aau, 0x5cb0a9dcu, 0x76f988dau,
    0x983e5152u, 0xa831c66du, 0xb00327c8u, 0xbf597fc7u,
    0xc6e00bf3u, 0xd5a79147u, 0x06ca6351u, 0x14292967u,
    0x27b70a85u, 0x2e1b2138u, 0x4d2c6dfcu, 0x53380d13u,
    0x650a7354u, 0x766a0abbu, 0x81c2c92eu, 0x92722c85u,
    0xa2bfe8a1u, 0xa81a664bu, 0xc24b8b70u, 0xc76c51a3u,
    0xd192e819u, 0xd6990624u, 0xf40e3585u, 0x106aa070u,
    0x19a4c116u, 0x1e376c08u, 0x2748774cu, 0x34b0bcb5u,
    0x391c0cb3u, 0x4ed8aa4au, 0x5b9cca4fu, 0x682e6ff3u,
    0x748f82eeu, 0x78a5636fu, 0x84c87814u, 0x8cc70208u,
    0x90befffau, 0xa4506cebu, 0xbef9a3f7u, 0xc67178f2u,
};

static uint32_t rotate_right(uint32_t value, unsigned int count) {
  return (value >> count) | (value << (32u - count));
}

static void sha256_transform(sha256_context *context,
                             const unsigned char *block) {
  uint32_t words[64];
  uint32_t a;
  uint32_t b;
  uint32_t c;
  uint32_t d;
  uint32_t e;
  uint32_t f;
  uint32_t g;
  uint32_t h;
  int index;

  for (index = 0; index < 16; ++index) {
    words[index] = ((uint32_t)block[4 * index] << 24) |
                   ((uint32_t)block[4 * index + 1] << 16) |
                   ((uint32_t)block[4 * index + 2] << 8) |
                   (uint32_t)block[4 * index + 3];
  }
  for (index = 16; index < 64; ++index) {
    uint32_t sigma_zero = rotate_right(words[index - 15], 7) ^
                          rotate_right(words[index - 15], 18) ^
                          (words[index - 15] >> 3);
    uint32_t sigma_one = rotate_right(words[index - 2], 17) ^
                         rotate_right(words[index - 2], 19) ^
                         (words[index - 2] >> 10);
    words[index] = words[index - 16] + sigma_zero + words[index - 7] +
                   sigma_one;
  }

  a = context->state[0];
  b = context->state[1];
  c = context->state[2];
  d = context->state[3];
  e = context->state[4];
  f = context->state[5];
  g = context->state[6];
  h = context->state[7];
  for (index = 0; index < 64; ++index) {
    uint32_t choice = (e & f) ^ ((~e) & g);
    uint32_t majority = (a & b) ^ (a & c) ^ (b & c);
    uint32_t capital_sigma_zero =
        rotate_right(a, 2) ^ rotate_right(a, 13) ^ rotate_right(a, 22);
    uint32_t capital_sigma_one =
        rotate_right(e, 6) ^ rotate_right(e, 11) ^ rotate_right(e, 25);
    uint32_t first = h + capital_sigma_one + choice +
                     sha256_round_constants[index] + words[index];
    uint32_t second = capital_sigma_zero + majority;

    h = g;
    g = f;
    f = e;
    e = d + first;
    d = c;
    c = b;
    b = a;
    a = first + second;
  }
  context->state[0] += a;
  context->state[1] += b;
  context->state[2] += c;
  context->state[3] += d;
  context->state[4] += e;
  context->state[5] += f;
  context->state[6] += g;
  context->state[7] += h;
}

static void sha256_initialize(sha256_context *context) {
  static const uint32_t initial_state[8] = {
      0x6a09e667u, 0xbb67ae85u, 0x3c6ef372u, 0xa54ff53au,
      0x510e527fu, 0x9b05688cu, 0x1f83d9abu, 0x5be0cd19u,
  };

  memcpy(context->state, initial_state, sizeof(initial_state));
  context->bit_count = 0;
  context->block_bytes = 0;
}

static void sha256_update(sha256_context *context, const unsigned char *input,
                          size_t input_bytes) {
  context->bit_count += (uint64_t)input_bytes * 8u;
  while (input_bytes > 0) {
    size_t available = sizeof(context->block) - context->block_bytes;
    size_t copied = input_bytes < available ? input_bytes : available;

    memcpy(context->block + context->block_bytes, input, copied);
    context->block_bytes += copied;
    input += copied;
    input_bytes -= copied;
    if (context->block_bytes == sizeof(context->block)) {
      sha256_transform(context, context->block);
      context->block_bytes = 0;
    }
  }
}

static void sha256_finalize(sha256_context *context,
                            unsigned char digest[32]) {
  uint64_t original_bit_count = context->bit_count;
  unsigned char marker = 0x80;
  unsigned char zero = 0;
  unsigned char encoded_length[8];
  int index;

  sha256_update(context, &marker, 1);
  while (context->block_bytes != 56) {
    sha256_update(context, &zero, 1);
  }
  for (index = 0; index < 8; ++index) {
    encoded_length[7 - index] =
        (unsigned char)(original_bit_count >> (8 * index));
  }
  sha256_update(context, encoded_length, sizeof(encoded_length));
  for (index = 0; index < 8; ++index) {
    int byte_index;
    for (byte_index = 0; byte_index < 4; ++byte_index) {
      digest[4 * index + byte_index] =
          (unsigned char)(context->state[index] >> (24 - 8 * byte_index));
    }
  }
}

static int sha256_hex_equal(const unsigned char digest[32],
                            const char *expected) {
  static const char hexadecimal[] = "0123456789abcdef";
  char actual[65];
  int index;

  if (strlen(expected) != 64) {
    return 0;
  }
  for (index = 0; index < 32; ++index) {
    actual[2 * index] = hexadecimal[digest[index] >> 4];
    actual[2 * index + 1] = hexadecimal[digest[index] & 15];
  }
  actual[64] = '\0';
  return memcmp(actual, expected, 64) == 0;
}

static int verify_fd_pin(int descriptor, off_t expected_size,
                         const char *expected_sha256) {
  unsigned char buffer[64 * 1024];
  unsigned char digest[32];
  sha256_context context;
  off_t total = 0;
  ssize_t observed;

  if (expected_size <= 0 || lseek(descriptor, 0, SEEK_SET) < 0) {
    return -1;
  }
  sha256_initialize(&context);
  while ((observed = read(descriptor, buffer, sizeof(buffer))) > 0) {
    if (total > expected_size || observed > expected_size - total) {
      return -1;
    }
    total += observed;
    sha256_update(&context, buffer, (size_t)observed);
  }
  if (observed < 0 || total != expected_size ||
      lseek(descriptor, 0, SEEK_SET) < 0) {
    return -1;
  }
  sha256_finalize(&context, digest);
  return sha256_hex_equal(digest, expected_sha256) ? 0 : -1;
}

static int fail(const char *message) {
  size_t length = strlen(message);
  (void)!write(STDERR_FILENO, message, length);
  (void)!write(STDERR_FILENO, "\n", 1);
  return FAILURE_EXIT;
}

static int verify_regular_fd(int descriptor, mode_t exact_mode,
                             struct stat *result) {
  struct stat metadata;

  if (fstat(descriptor, &metadata) != 0 || !S_ISREG(metadata.st_mode) ||
      metadata.st_nlink != 1 || metadata.st_uid != 0 || metadata.st_gid != 0 ||
      (metadata.st_mode & 07777) != exact_mode) {
    return -1;
  }
  if (result != NULL) {
    *result = metadata;
  }
  return 0;
}

static int same_file_identity(const struct stat *left,
                              const struct stat *right) {
  return left->st_dev == right->st_dev && left->st_ino == right->st_ino &&
         left->st_size == right->st_size && left->st_mode == right->st_mode &&
         left->st_nlink == right->st_nlink && left->st_uid == right->st_uid &&
         left->st_gid == right->st_gid &&
         left->st_mtim.tv_sec == right->st_mtim.tv_sec &&
         left->st_mtim.tv_nsec == right->st_mtim.tv_nsec &&
         left->st_ctim.tv_sec == right->st_ctim.tv_sec &&
         left->st_ctim.tv_nsec == right->st_ctim.tv_nsec;
}

static int open_verified_regular(const char *path, mode_t exact_mode,
                                 struct stat *metadata) {
  int descriptor = open(path, O_RDONLY | O_NOFOLLOW | O_CLOEXEC);

  if (descriptor < 0 || verify_regular_fd(descriptor, exact_mode, metadata) != 0) {
    if (descriptor >= 0) {
      (void)close(descriptor);
    }
    return -1;
  }
  return descriptor;
}

static int verify_pinned_regular_fd(int descriptor, mode_t exact_mode,
                                    off_t expected_size,
                                    const char *expected_sha256) {
  struct stat before;
  struct stat after;

  if (verify_regular_fd(descriptor, exact_mode, &before) != 0 ||
      before.st_size != expected_size ||
      verify_fd_pin(descriptor, expected_size, expected_sha256) != 0 ||
      verify_regular_fd(descriptor, exact_mode, &after) != 0 ||
      !same_file_identity(&before, &after)) {
    return -1;
  }
  return 0;
}

static int open_verified_pinned_regular(const char *path, mode_t exact_mode,
                                        off_t expected_size,
                                        const char *expected_sha256) {
  int descriptor = open(path, O_RDONLY | O_NOFOLLOW | O_CLOEXEC);

  if (descriptor < 0 ||
      verify_pinned_regular_fd(descriptor, exact_mode, expected_size,
                               expected_sha256) != 0) {
    if (descriptor >= 0) {
      (void)close(descriptor);
    }
    return -1;
  }
  return descriptor;
}

static int clear_close_on_exec(int descriptor) {
  int descriptor_flags = fcntl(descriptor, F_GETFD);

  if (descriptor_flags < 0 ||
      fcntl(descriptor, F_SETFD, descriptor_flags & ~FD_CLOEXEC) != 0) {
    return -1;
  }
  return 0;
}

int main(int argc, char **argv) {
  const char *operation;
  const char *acknowledgement;
  struct stat expected_self_metadata;
  struct stat live_self_metadata;
  struct stat final_self_metadata;
  struct stat proc_link_metadata;
  int expected_self_descriptor;
  int proc_link_descriptor;
  int live_self_descriptor;
  int final_self_descriptor;
  int python_descriptor;
  int helper_descriptor;
  char helper_fd_path[64];
  int helper_fd_path_length;

  if (argc != 3) {
    return fail(
        "R8_ADMIN_LAUNCHER: exactly one operation and acknowledgement required");
  }
  if (strcmp(argv[1], PUBLISH_OPERATION) == 0) {
    operation = PUBLISH_OPERATION;
    acknowledgement = PUBLISH_ACKNOWLEDGEMENT;
  } else if (strcmp(argv[1], RECONCILE_OPERATION) == 0) {
    operation = RECONCILE_OPERATION;
    acknowledgement = RECONCILE_ACKNOWLEDGEMENT;
  } else {
    return fail("R8_ADMIN_LAUNCHER: operation differs from compiled stage");
  }
  if (strcmp(argv[2], acknowledgement) != 0) {
    return fail("R8_ADMIN_LAUNCHER: acknowledgement differs");
  }
  if (geteuid() != 0) {
    return fail("R8_ADMIN_LAUNCHER: root EUID required");
  }

  expected_self_descriptor =
      open_verified_regular(EXPECTED_SELF_PATH, SELF_MODE,
                            &expected_self_metadata);
  if (expected_self_descriptor < 0) {
    return fail("R8_ADMIN_LAUNCHER: installed self metadata differs");
  }

  /*
   * O_NOFOLLOW deliberately opens and holds the procfs magic link itself.
   * Linux cannot both O_NOFOLLOW that link and return its regular-file target,
   * so the second held descriptor performs the one intentional procfs follow.
   * /proc/self/exe cannot be retargeted during the lifetime of this process.
   */
  proc_link_descriptor =
      open("/proc/self/exe", O_PATH | O_NOFOLLOW | O_CLOEXEC);
  if (proc_link_descriptor < 0 ||
      fstat(proc_link_descriptor, &proc_link_metadata) != 0 ||
      !S_ISLNK(proc_link_metadata.st_mode) || proc_link_metadata.st_nlink != 1 ||
      proc_link_metadata.st_uid != 0 || proc_link_metadata.st_gid != 0) {
    return fail("R8_ADMIN_LAUNCHER: proc self link metadata differs");
  }
  live_self_descriptor = open("/proc/self/exe", O_RDONLY | O_CLOEXEC);
  if (live_self_descriptor < 0 ||
      verify_regular_fd(live_self_descriptor, SELF_MODE, &live_self_metadata) !=
          0 ||
      !same_file_identity(&expected_self_metadata, &live_self_metadata)) {
    return fail("R8_ADMIN_LAUNCHER: live self identity differs");
  }

  python_descriptor = open_verified_pinned_regular(
      PYTHON_PATH, PYTHON_MODE, (off_t)EXPECTED_PYTHON_SIZE,
      EXPECTED_PYTHON_SHA256);
  if (python_descriptor < 0) {
    return fail("R8_ADMIN_LAUNCHER: Python metadata differs");
  }
  helper_descriptor = open_verified_pinned_regular(
      CORE_HELPER_PATH, CORE_HELPER_MODE, (off_t)EXPECTED_HELPER_SIZE,
      EXPECTED_HELPER_SHA256);
  if (helper_descriptor < 0 || clear_close_on_exec(helper_descriptor) != 0) {
    return fail("R8_ADMIN_LAUNCHER: core helper metadata differs");
  }

  helper_fd_path_length =
      snprintf(helper_fd_path, sizeof(helper_fd_path), "/proc/self/fd/%d",
               helper_descriptor);
  if (helper_fd_path_length < 0 ||
      (size_t)helper_fd_path_length >= sizeof(helper_fd_path)) {
    return fail("R8_ADMIN_LAUNCHER: helper descriptor path failed");
  }
  if (verify_pinned_regular_fd(
          python_descriptor, PYTHON_MODE, (off_t)EXPECTED_PYTHON_SIZE,
          EXPECTED_PYTHON_SHA256) != 0 ||
      verify_pinned_regular_fd(
          helper_descriptor, CORE_HELPER_MODE, (off_t)EXPECTED_HELPER_SIZE,
          EXPECTED_HELPER_SHA256) != 0) {
    return fail("R8_ADMIN_LAUNCHER: held executable pin drifted");
  }
  final_self_descriptor =
      open_verified_regular(EXPECTED_SELF_PATH, SELF_MODE, &final_self_metadata);
  if (final_self_descriptor < 0 ||
      verify_regular_fd(expected_self_descriptor, SELF_MODE, NULL) != 0 ||
      verify_regular_fd(live_self_descriptor, SELF_MODE, NULL) != 0 ||
      !same_file_identity(&expected_self_metadata, &final_self_metadata) ||
      !same_file_identity(&live_self_metadata, &final_self_metadata)) {
    return fail("R8_ADMIN_LAUNCHER: installed self identity drifted");
  }

  {
    char *const child_argv[] = {
        PYTHON_PATH,
        "-I",
        "-B",
        helper_fd_path,
        (char *)operation,
        "--acknowledgement",
        (char *)acknowledgement,
        NULL,
    };
    char *const child_env[] = {
        "PATH=/usr/bin:/bin",
        "HOME=/nonexistent",
        "LANG=C.UTF-8",
        "PYTHONNOUSERSITE=1",
        "PYTHONDONTWRITEBYTECODE=1",
        NULL,
    };

    (void)syscall(SYS_execveat, python_descriptor, "", child_argv, child_env,
                  AT_EMPTY_PATH);
  }
  return fail("R8_ADMIN_LAUNCHER: held-Python execveat failed");
}
