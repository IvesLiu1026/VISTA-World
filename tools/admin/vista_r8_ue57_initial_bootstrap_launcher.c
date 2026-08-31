#define _GNU_SOURCE

#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/file.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <unistd.h>

/*
 * Static held-FD entry point for the initial four-root bootstrap.  The binary
 * intentionally does not embed its own hash or the input-pin hash: input-pin
 * is created after this binary and binds its resulting pin.  Before executing
 * the pinned helper, this launcher hashes itself and proves that the canonical
 * input document binds that self pin, the compiled helper pin, and the
 * compiled Python pin.  The helper performs the full closed-schema validation
 * again before any write.
 */
#ifndef EXPECTED_HELPER_SHA256
#error "EXPECTED_HELPER_SHA256 is required"
#endif
#ifndef EXPECTED_HELPER_SIZE
#error "EXPECTED_HELPER_SIZE is required"
#endif
#ifndef EXPECTED_PYTHON_SHA256
#error "EXPECTED_PYTHON_SHA256 is required"
#endif
#ifndef EXPECTED_PYTHON_SIZE
#error "EXPECTED_PYTHON_SIZE is required"
#endif

_Static_assert(sizeof(EXPECTED_HELPER_SHA256) == 65,
               "helper SHA-256 must contain 64 bytes");
_Static_assert(sizeof(EXPECTED_PYTHON_SHA256) == 65,
               "Python SHA-256 must contain 64 bytes");
_Static_assert(EXPECTED_HELPER_SIZE > 0, "helper size must be positive");
_Static_assert(EXPECTED_PYTHON_SIZE > 0, "Python size must be positive");

#define INSTALLED_ROOT_DEFAULT "/root/vista-r8-ue57-initial-bootstrap-r2"
#define PYTHON_PATH_DEFAULT "/usr/bin/python3.10"
#define LAUNCHER_NAME "bootstrap-r8-ue57-initial-authorities"
#define HELPER_NAME "vista_r8_ue57_initial_bootstrap.py"
#define INPUT_NAME "input-pin.json"
#define LOCK_NAME ".bootstrap.lock"

#define PUBLISH_OPERATION "publish-initial-authorities"
#define RECONCILE_OPERATION "reconcile-initial-authorities"
#define RESUME_OPERATION "resume-initial-authorities"
#define PUBLISH_ACK                                                            \
  "I acknowledge one irreversible append-only publication of the four "       \
  "externally reviewed VISTA R8 UE 5.7 initial authorities from an empty "     \
  "prefix."
#define RECONCILE_ACK                                                          \
  "I acknowledge candidate-free audit and fsync reconciliation of the "       \
  "existing VISTA R8 UE 5.7 initial-authority prefix without creating, "       \
  "deleting, or repairing any root."
#define RESUME_ACK                                                             \
  "I acknowledge candidate-free reconciliation followed by append-only "      \
  "resume of the externally reviewed VISTA R8 UE 5.7 initial-authority "       \
  "prefix."

#ifdef VISTA_R8_INITIAL_BOOTSTRAP_TESTING
#ifndef VISTA_R8_INITIAL_TEST_ROOT
#error "VISTA_R8_INITIAL_TEST_ROOT is required"
#endif
#ifndef VISTA_R8_INITIAL_TEST_PYTHON
#error "VISTA_R8_INITIAL_TEST_PYTHON is required"
#endif
#ifndef VISTA_R8_INITIAL_TEST_REQUIRED_EUID
#error "VISTA_R8_INITIAL_TEST_REQUIRED_EUID is required"
#endif
#ifndef VISTA_R8_INITIAL_TEST_REQUIRED_EGID
#error "VISTA_R8_INITIAL_TEST_REQUIRED_EGID is required"
#endif
#ifndef VISTA_R8_INITIAL_TEST_OWNER_UID
#error "VISTA_R8_INITIAL_TEST_OWNER_UID is required"
#endif
#ifndef VISTA_R8_INITIAL_TEST_OWNER_GID
#error "VISTA_R8_INITIAL_TEST_OWNER_GID is required"
#endif
#ifndef VISTA_R8_INITIAL_TEST_PYTHON_UID
#error "VISTA_R8_INITIAL_TEST_PYTHON_UID is required"
#endif
#ifndef VISTA_R8_INITIAL_TEST_PYTHON_GID
#error "VISTA_R8_INITIAL_TEST_PYTHON_GID is required"
#endif
#define INSTALLED_ROOT VISTA_R8_INITIAL_TEST_ROOT
#define PYTHON_PATH VISTA_R8_INITIAL_TEST_PYTHON
#define REQUIRED_EUID ((uid_t)VISTA_R8_INITIAL_TEST_REQUIRED_EUID)
#define REQUIRED_EGID ((gid_t)VISTA_R8_INITIAL_TEST_REQUIRED_EGID)
#define AUTHORITY_UID ((uid_t)VISTA_R8_INITIAL_TEST_OWNER_UID)
#define AUTHORITY_GID ((gid_t)VISTA_R8_INITIAL_TEST_OWNER_GID)
#define PYTHON_UID ((uid_t)VISTA_R8_INITIAL_TEST_PYTHON_UID)
#define PYTHON_GID ((gid_t)VISTA_R8_INITIAL_TEST_PYTHON_GID)
#else
#define INSTALLED_ROOT INSTALLED_ROOT_DEFAULT
#define PYTHON_PATH PYTHON_PATH_DEFAULT
#define REQUIRED_EUID ((uid_t)0)
#define REQUIRED_EGID ((gid_t)0)
#define AUTHORITY_UID ((uid_t)0)
#define AUTHORITY_GID ((gid_t)0)
#define PYTHON_UID ((uid_t)0)
#define PYTHON_GID ((gid_t)0)
#endif

enum {
  FAILURE_EXIT = 126,
  ROOT_MODE = 0555,
  LAUNCHER_MODE = 0500,
  HELPER_MODE = 0500,
  INPUT_MODE = 0444,
  LOCK_MODE = 0600,
  PYTHON_MODE = 0755,
  MAX_PINNED_BYTES = 16 * 1024 * 1024,
};

typedef struct {
  uint32_t state[8];
  uint64_t bit_count;
  unsigned char block[64];
  size_t block_bytes;
} sha256_context;

typedef struct {
  const char *sha256;
  off_t size_bytes;
} fixed_pin;

static const uint32_t round_constants[64] = {
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

static void transform(sha256_context *context, const unsigned char *block) {
  uint32_t words[64];
  uint32_t a, b, c, d, e, f, g, h;
  int index;
  for (index = 0; index < 16; ++index) {
    words[index] = ((uint32_t)block[4 * index] << 24) |
                   ((uint32_t)block[4 * index + 1] << 16) |
                   ((uint32_t)block[4 * index + 2] << 8) |
                   (uint32_t)block[4 * index + 3];
  }
  for (index = 16; index < 64; ++index) {
    uint32_t s0 = rotate_right(words[index - 15], 7) ^
                  rotate_right(words[index - 15], 18) ^
                  (words[index - 15] >> 3);
    uint32_t s1 = rotate_right(words[index - 2], 17) ^
                  rotate_right(words[index - 2], 19) ^
                  (words[index - 2] >> 10);
    words[index] = words[index - 16] + s0 + words[index - 7] + s1;
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
    uint32_t s0 =
        rotate_right(a, 2) ^ rotate_right(a, 13) ^ rotate_right(a, 22);
    uint32_t s1 =
        rotate_right(e, 6) ^ rotate_right(e, 11) ^ rotate_right(e, 25);
    uint32_t first =
        h + s1 + choice + round_constants[index] + words[index];
    uint32_t second = s0 + majority;
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

static void initialize(sha256_context *context) {
  static const uint32_t initial[8] = {
      0x6a09e667u, 0xbb67ae85u, 0x3c6ef372u, 0xa54ff53au,
      0x510e527fu, 0x9b05688cu, 0x1f83d9abu, 0x5be0cd19u,
  };
  memcpy(context->state, initial, sizeof(initial));
  context->bit_count = 0;
  context->block_bytes = 0;
}

static void update(sha256_context *context, const unsigned char *input,
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
      transform(context, context->block);
      context->block_bytes = 0;
    }
  }
}

static void finalize(sha256_context *context, unsigned char digest[32]) {
  uint64_t original_bits = context->bit_count;
  unsigned char marker = 0x80;
  unsigned char zero = 0;
  unsigned char length[8];
  int index;
  update(context, &marker, 1);
  while (context->block_bytes != 56) {
    update(context, &zero, 1);
  }
  for (index = 0; index < 8; ++index) {
    length[7 - index] = (unsigned char)(original_bits >> (8 * index));
  }
  update(context, length, sizeof(length));
  for (index = 0; index < 8; ++index) {
    int byte_index;
    for (byte_index = 0; byte_index < 4; ++byte_index) {
      digest[4 * index + byte_index] =
          (unsigned char)(context->state[index] >> (24 - 8 * byte_index));
    }
  }
}

static int valid_sha256(const char *value) {
  size_t index;
  if (strlen(value) != 64) {
    return 0;
  }
  for (index = 0; index < 64; ++index) {
    if (!((value[index] >= '0' && value[index] <= '9') ||
          (value[index] >= 'a' && value[index] <= 'f'))) {
      return 0;
    }
  }
  return 1;
}

static int hash_descriptor(int descriptor, char output[65], off_t *size_result) {
  static const char hexadecimal[] = "0123456789abcdef";
  unsigned char buffer[64 * 1024];
  unsigned char digest[32];
  sha256_context context;
  struct stat metadata;
  off_t total = 0;
  ssize_t observed;
  int index;
  if (fstat(descriptor, &metadata) != 0 || !S_ISREG(metadata.st_mode) ||
      metadata.st_size <= 0 || metadata.st_size > MAX_PINNED_BYTES ||
      lseek(descriptor, 0, SEEK_SET) < 0) {
    return -1;
  }
  initialize(&context);
  while (total < metadata.st_size) {
    size_t remaining = (size_t)(metadata.st_size - total);
    size_t requested = remaining < sizeof(buffer) ? remaining : sizeof(buffer);
    observed = read(descriptor, buffer, requested);
    if (observed <= 0) {
      return -1;
    }
    total += observed;
    update(&context, buffer, (size_t)observed);
  }
  if (read(descriptor, buffer, 1) != 0 || lseek(descriptor, 0, SEEK_SET) < 0) {
    return -1;
  }
  finalize(&context, digest);
  for (index = 0; index < 32; ++index) {
    output[2 * index] = hexadecimal[digest[index] >> 4];
    output[2 * index + 1] = hexadecimal[digest[index] & 15];
  }
  output[64] = '\0';
  *size_result = total;
  return 0;
}

static int verify_pin(int descriptor, const fixed_pin *pin) {
  char digest[65];
  off_t size_bytes;
  return valid_sha256(pin->sha256) &&
                 hash_descriptor(descriptor, digest, &size_bytes) == 0 &&
                 size_bytes == pin->size_bytes &&
                 strcmp(digest, pin->sha256) == 0
             ? 0
             : -1;
}

static int fail(const char *message) {
  (void)!write(STDERR_FILENO, message, strlen(message));
  (void)!write(STDERR_FILENO, "\n", 1);
  return FAILURE_EXIT;
}

static int same_identity(const struct stat *left, const struct stat *right) {
  return left->st_dev == right->st_dev && left->st_ino == right->st_ino &&
         left->st_mode == right->st_mode && left->st_uid == right->st_uid &&
         left->st_gid == right->st_gid && left->st_nlink == right->st_nlink &&
         left->st_size == right->st_size &&
         left->st_mtim.tv_sec == right->st_mtim.tv_sec &&
         left->st_mtim.tv_nsec == right->st_mtim.tv_nsec &&
         left->st_ctim.tv_sec == right->st_ctim.tv_sec &&
         left->st_ctim.tv_nsec == right->st_ctim.tv_nsec;
}

static int verify_directory(int descriptor, mode_t mode, uid_t uid, gid_t gid,
                            int links, struct stat *result) {
  struct stat metadata;
  if (fstat(descriptor, &metadata) != 0 || !S_ISDIR(metadata.st_mode) ||
      (metadata.st_mode & 07777) != mode || metadata.st_uid != uid ||
      metadata.st_gid != gid ||
      (links >= 0 && metadata.st_nlink != (nlink_t)links)) {
    return -1;
  }
  if (result != NULL) {
    *result = metadata;
  }
  return 0;
}

static int verify_regular(int descriptor, mode_t mode, uid_t uid, gid_t gid,
                          off_t exact_size, struct stat *result) {
  struct stat metadata;
  if (fstat(descriptor, &metadata) != 0 || !S_ISREG(metadata.st_mode) ||
      metadata.st_nlink != 1 || (metadata.st_mode & 07777) != mode ||
      metadata.st_uid != uid || metadata.st_gid != gid ||
      (exact_size >= 0 && metadata.st_size != exact_size)) {
    return -1;
  }
  if (result != NULL) {
    *result = metadata;
  }
  return 0;
}

static int open_parent_nofollow(const char *path, int *parent_result,
                                char name_result[NAME_MAX + 1]) {
  char copy[PATH_MAX];
  size_t length;
  size_t cursor = 1;
  int current;
  if (path == NULL || path[0] != '/' || path[1] == '\0') {
    return -1;
  }
  length = strlen(path);
  if (length >= sizeof(copy) || path[length - 1] == '/') {
    return -1;
  }
  memcpy(copy, path, length + 1);
  current = open("/", O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
  if (current < 0) {
    return -1;
  }
  while (cursor < length) {
    size_t start = cursor;
    size_t component_length;
    int last;
    int next;
    while (cursor < length && copy[cursor] != '/') {
      ++cursor;
    }
    component_length = cursor - start;
    last = cursor == length;
    if (component_length == 0 || component_length > NAME_MAX ||
        (component_length == 1 && copy[start] == '.') ||
        (component_length == 2 && copy[start] == '.' &&
         copy[start + 1] == '.')) {
      (void)close(current);
      return -1;
    }
    copy[start + component_length] = '\0';
    if (last) {
      memcpy(name_result, copy + start, component_length + 1);
      *parent_result = current;
      return 0;
    }
    next = openat(current, copy + start,
                  O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    if (next < 0) {
      (void)close(current);
      return -1;
    }
    (void)close(current);
    current = next;
    ++cursor;
  }
  (void)close(current);
  return -1;
}

static int open_regular_path(const char *path, mode_t mode, uid_t uid,
                             gid_t gid, struct stat *metadata) {
  char name[NAME_MAX + 1];
  int parent;
  int descriptor;
  if (open_parent_nofollow(path, &parent, name) != 0) {
    return -1;
  }
  descriptor = openat(parent, name,
                      O_RDONLY | O_NONBLOCK | O_NOFOLLOW | O_CLOEXEC);
  (void)close(parent);
  if (descriptor < 0 ||
      verify_regular(descriptor, mode, uid, gid, -1, metadata) != 0) {
    if (descriptor >= 0) {
      (void)close(descriptor);
    }
    return -1;
  }
  return descriptor;
}

static int exact_inventory(int root_descriptor) {
  const char *names[4] = {LAUNCHER_NAME, HELPER_NAME, INPUT_NAME, LOCK_NAME};
  unsigned char seen[4] = {0, 0, 0, 0};
  int duplicate = openat(root_descriptor, ".",
                         O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
  DIR *stream;
  struct dirent *entry;
  size_t observed = 0;
  if (duplicate < 0) {
    return -1;
  }
  stream = fdopendir(duplicate);
  if (stream == NULL) {
    (void)close(duplicate);
    return -1;
  }
  errno = 0;
  while ((entry = readdir(stream)) != NULL) {
    int matched = 0;
    int index;
    if (strcmp(entry->d_name, ".") == 0 || strcmp(entry->d_name, "..") == 0) {
      continue;
    }
    for (index = 0; index < 4; ++index) {
      if (!seen[index] && strcmp(entry->d_name, names[index]) == 0) {
        seen[index] = 1;
        matched = 1;
        ++observed;
        break;
      }
    }
    if (!matched) {
      (void)closedir(stream);
      return -1;
    }
  }
  if (errno != 0 || closedir(stream) != 0 || observed != 4) {
    return -1;
  }
  return 0;
}

static int clear_close_on_exec(int descriptor) {
  int flags = fcntl(descriptor, F_GETFD);
  return flags < 0 ||
                 fcntl(descriptor, F_SETFD, flags & ~FD_CLOEXEC) != 0
             ? -1
             : 0;
}

static int count_bytes(const unsigned char *haystack, size_t haystack_bytes,
                       const char *needle) {
  size_t needle_bytes = strlen(needle);
  size_t offset;
  int count = 0;
  if (needle_bytes == 0 || needle_bytes > haystack_bytes) {
    return 0;
  }
  for (offset = 0; offset + needle_bytes <= haystack_bytes; ++offset) {
    if (memcmp(haystack + offset, needle, needle_bytes) == 0) {
      ++count;
    }
  }
  return count;
}

static int input_binds_components(int descriptor, const char *self_sha,
                                  off_t self_size) {
  struct stat metadata;
  unsigned char *raw = NULL;
  size_t offset = 0;
  char self_needle[PATH_MAX + 180];
  char helper_needle[PATH_MAX + 180];
  char python_needle[PATH_MAX + 180];
  int result = -1;
  if (fstat(descriptor, &metadata) != 0 || metadata.st_size <= 0 ||
      metadata.st_size > MAX_PINNED_BYTES || lseek(descriptor, 0, SEEK_SET) < 0) {
    return -1;
  }
  raw = malloc((size_t)metadata.st_size);
  if (raw == NULL) {
    return -1;
  }
  while (offset < (size_t)metadata.st_size) {
    ssize_t observed =
        read(descriptor, raw + offset, (size_t)metadata.st_size - offset);
    if (observed <= 0) {
      goto finished;
    }
    offset += (size_t)observed;
  }
  if (read(descriptor, raw, 1) != 0 || lseek(descriptor, 0, SEEK_SET) < 0) {
    goto finished;
  }
  if (snprintf(self_needle, sizeof(self_needle),
               "\"path\":\"%s/%s\",\"pin\":{\"sha256\":\"%s\","
               "\"size_bytes\":%lld}",
               INSTALLED_ROOT, LAUNCHER_NAME, self_sha,
               (long long)self_size) < 0 ||
      snprintf(helper_needle, sizeof(helper_needle),
               "\"path\":\"%s/%s\",\"pin\":{\"sha256\":\"%s\","
               "\"size_bytes\":%lld}",
               INSTALLED_ROOT, HELPER_NAME, EXPECTED_HELPER_SHA256,
               (long long)EXPECTED_HELPER_SIZE) < 0 ||
      snprintf(python_needle, sizeof(python_needle),
               "\"path\":\"%s\",\"pin\":{\"sha256\":\"%s\","
               "\"size_bytes\":%lld}",
               PYTHON_PATH, EXPECTED_PYTHON_SHA256,
               (long long)EXPECTED_PYTHON_SIZE) < 0) {
    goto finished;
  }
  if (count_bytes(raw, (size_t)metadata.st_size,
                  "\"schema\":\"vista.r8-ue57-initial-bootstrap-input-pin/v2\"") ==
          1 &&
      count_bytes(raw, (size_t)metadata.st_size, self_needle) == 1 &&
      count_bytes(raw, (size_t)metadata.st_size, helper_needle) == 1 &&
      count_bytes(raw, (size_t)metadata.st_size, python_needle) == 1) {
    result = 0;
  }
finished:
  free(raw);
  return result;
}

static int production_ancestors_are_exact(void) {
#ifdef VISTA_R8_INITIAL_BOOTSTRAP_TESTING
  return 0;
#else
  int slash = open("/", O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
  int root;
  if (slash < 0 || verify_directory(slash, 0755, 0, 0, -1, NULL) != 0) {
    return -1;
  }
  root = openat(slash, "root", O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
  (void)close(slash);
  if (root < 0 || verify_directory(root, 0700, 0, 0, -1, NULL) != 0) {
    if (root >= 0) {
      (void)close(root);
    }
    return -1;
  }
  (void)close(root);
  return 0;
#endif
}

int main(int argc, char **argv) {
  const char *operation;
  const char *acknowledgement;
  fixed_pin helper_pin = {EXPECTED_HELPER_SHA256, (off_t)EXPECTED_HELPER_SIZE};
  fixed_pin python_pin = {EXPECTED_PYTHON_SHA256, (off_t)EXPECTED_PYTHON_SIZE};
  struct stat root_info, self_info, live_self_info, helper_info, input_info;
  struct stat lock_info, python_info, reopened_root_info;
  char root_name[NAME_MAX + 1];
  char self_sha[65];
  off_t self_size;
  int parent = -1;
  int root_fd = -1, reopened_root_fd = -1;
  int self_fd = -1, live_self_fd = -1, helper_fd = -1, input_fd = -1;
  int lock_fd = -1, python_fd = -1;
  char helper_path[64], launcher_text[32], helper_text[32], input_text[32];
  char python_text[32], lock_text[32];

  if (argc != 3) {
    return fail("INITIAL_BOOTSTRAP_LAUNCHER: exact argc 3 required");
  }
  operation = argv[1];
  acknowledgement = argv[2];
  if ((strcmp(operation, PUBLISH_OPERATION) == 0 &&
       strcmp(acknowledgement, PUBLISH_ACK) != 0) ||
      (strcmp(operation, RECONCILE_OPERATION) == 0 &&
       strcmp(acknowledgement, RECONCILE_ACK) != 0) ||
      (strcmp(operation, RESUME_OPERATION) == 0 &&
       strcmp(acknowledgement, RESUME_ACK) != 0) ||
      (strcmp(operation, PUBLISH_OPERATION) != 0 &&
       strcmp(operation, RECONCILE_OPERATION) != 0 &&
       strcmp(operation, RESUME_OPERATION) != 0)) {
    return fail("INITIAL_BOOTSTRAP_LAUNCHER: operation or acknowledgement differs");
  }
  if (geteuid() != REQUIRED_EUID || getegid() != REQUIRED_EGID) {
    return fail("INITIAL_BOOTSTRAP_LAUNCHER: required EUID/EGID differs");
  }
  if (!valid_sha256(EXPECTED_HELPER_SHA256) ||
      !valid_sha256(EXPECTED_PYTHON_SHA256) ||
      production_ancestors_are_exact() != 0 ||
      open_parent_nofollow(INSTALLED_ROOT, &parent, root_name) != 0) {
    return fail("INITIAL_BOOTSTRAP_LAUNCHER: fixed ancestor contract differs");
  }
  root_fd = openat(parent, root_name,
                   O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
  (void)close(parent);
  parent = -1;
  if (root_fd < 0 ||
      verify_directory(root_fd, ROOT_MODE, AUTHORITY_UID, AUTHORITY_GID, 2,
                       &root_info) != 0 ||
      exact_inventory(root_fd) != 0) {
    return fail("INITIAL_BOOTSTRAP_LAUNCHER: installed root differs");
  }
  self_fd = openat(root_fd, LAUNCHER_NAME,
                   O_RDONLY | O_NONBLOCK | O_NOFOLLOW | O_CLOEXEC);
  helper_fd = openat(root_fd, HELPER_NAME,
                     O_RDONLY | O_NONBLOCK | O_NOFOLLOW | O_CLOEXEC);
  input_fd = openat(root_fd, INPUT_NAME,
                    O_RDONLY | O_NONBLOCK | O_NOFOLLOW | O_CLOEXEC);
  lock_fd = openat(root_fd, LOCK_NAME,
                   O_RDONLY | O_NONBLOCK | O_NOFOLLOW | O_CLOEXEC);
  if (self_fd < 0 || helper_fd < 0 || input_fd < 0 || lock_fd < 0 ||
      verify_regular(self_fd, LAUNCHER_MODE, AUTHORITY_UID, AUTHORITY_GID, -1,
                     &self_info) != 0 ||
      verify_regular(helper_fd, HELPER_MODE, AUTHORITY_UID, AUTHORITY_GID, -1,
                     &helper_info) != 0 ||
      verify_regular(input_fd, INPUT_MODE, AUTHORITY_UID, AUTHORITY_GID, -1,
                     &input_info) != 0 ||
      verify_regular(lock_fd, LOCK_MODE, AUTHORITY_UID, AUTHORITY_GID, 0,
                     &lock_info) != 0 ||
      verify_pin(helper_fd, &helper_pin) != 0 ||
      hash_descriptor(self_fd, self_sha, &self_size) != 0 ||
      input_binds_components(input_fd, self_sha, self_size) != 0) {
    return fail("INITIAL_BOOTSTRAP_LAUNCHER: installed files or input binding differ");
  }
  live_self_fd = open("/proc/self/exe", O_RDONLY | O_NONBLOCK | O_CLOEXEC);
  if (live_self_fd < 0 ||
      verify_regular(live_self_fd, LAUNCHER_MODE, AUTHORITY_UID, AUTHORITY_GID,
                     -1, &live_self_info) != 0 ||
      !same_identity(&self_info, &live_self_info)) {
    return fail("INITIAL_BOOTSTRAP_LAUNCHER: live self differs");
  }
  python_fd = open_regular_path(PYTHON_PATH, PYTHON_MODE, PYTHON_UID, PYTHON_GID,
                                &python_info);
  if (python_fd < 0 || verify_pin(python_fd, &python_pin) != 0) {
    return fail("INITIAL_BOOTSTRAP_LAUNCHER: pinned Python differs");
  }
  if (flock(lock_fd, LOCK_EX | LOCK_NB) != 0) {
    return fail("INITIAL_BOOTSTRAP_LAUNCHER: bootstrap lock is busy");
  }

  if (open_parent_nofollow(INSTALLED_ROOT, &parent, root_name) != 0) {
    return fail("INITIAL_BOOTSTRAP_LAUNCHER: installed root path drifted");
  }
  reopened_root_fd = openat(parent, root_name,
                            O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
  (void)close(parent);
  if (reopened_root_fd < 0 ||
      verify_directory(reopened_root_fd, ROOT_MODE, AUTHORITY_UID,
                       AUTHORITY_GID, 2, &reopened_root_info) != 0 ||
      !same_identity(&root_info, &reopened_root_info) ||
      exact_inventory(reopened_root_fd) != 0 ||
      verify_regular(self_fd, LAUNCHER_MODE, AUTHORITY_UID, AUTHORITY_GID, -1,
                     NULL) != 0 ||
      verify_regular(helper_fd, HELPER_MODE, AUTHORITY_UID, AUTHORITY_GID, -1,
                     NULL) != 0 ||
      verify_regular(input_fd, INPUT_MODE, AUTHORITY_UID, AUTHORITY_GID, -1,
                     NULL) != 0 ||
      verify_regular(lock_fd, LOCK_MODE, AUTHORITY_UID, AUTHORITY_GID, 0,
                     NULL) != 0 ||
      verify_pin(helper_fd, &helper_pin) != 0 ||
      input_binds_components(input_fd, self_sha, self_size) != 0 ||
      verify_pin(python_fd, &python_pin) != 0 ||
      verify_regular(live_self_fd, LAUNCHER_MODE, AUTHORITY_UID, AUTHORITY_GID,
                     -1, NULL) != 0 ||
      !same_identity(&self_info, &live_self_info)) {
    return fail("INITIAL_BOOTSTRAP_LAUNCHER: held identity drifted");
  }
  if (clear_close_on_exec(self_fd) != 0 ||
      clear_close_on_exec(helper_fd) != 0 ||
      clear_close_on_exec(input_fd) != 0 ||
      clear_close_on_exec(lock_fd) != 0 ||
      clear_close_on_exec(python_fd) != 0) {
    return fail("INITIAL_BOOTSTRAP_LAUNCHER: held descriptor setup failed");
  }
  if (snprintf(helper_path, sizeof(helper_path), "/proc/self/fd/%d", helper_fd) <
          0 ||
      snprintf(launcher_text, sizeof(launcher_text), "%d", self_fd) < 0 ||
      snprintf(helper_text, sizeof(helper_text), "%d", helper_fd) < 0 ||
      snprintf(input_text, sizeof(input_text), "%d", input_fd) < 0 ||
      snprintf(python_text, sizeof(python_text), "%d", python_fd) < 0 ||
      snprintf(lock_text, sizeof(lock_text), "%d", lock_fd) < 0) {
    return fail("INITIAL_BOOTSTRAP_LAUNCHER: descriptor formatting failed");
  }
  {
    char *const child_argv[] = {
        PYTHON_PATH,
        "-I",
        "-B",
        helper_path,
        (char *)operation,
        "--launcher-fd",
        launcher_text,
        "--helper-fd",
        helper_text,
        "--input-pin-fd",
        input_text,
        "--python-fd",
        python_text,
        "--lock-fd",
        lock_text,
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
    (void)syscall(SYS_execveat, python_fd, "", child_argv, child_env,
                  AT_EMPTY_PATH);
  }
  return fail("INITIAL_BOOTSTRAP_LAUNCHER: held-Python execveat failed");
}
