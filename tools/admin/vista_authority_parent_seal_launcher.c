#define _GNU_SOURCE

#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <unistd.h>

/*
 * Static, closed launcher for the one-shot /data/vista-authorities parent
 * sealer.  It uses no shell or external inspection utility.  The installed
 * root contains exactly this launcher and the pinned Python helper.
 */
#define INSTALLED_ROOT_DEFAULT "/root/vista-authority-parent-seal-r1"
#define LAUNCHER_NAME "launch-vista-authority-parent-seal"
#define HELPER_NAME "vista_authority_parent_seal.py"
#define PYTHON_PATH "/usr/bin/python3.10"
#define PYTHON_SHA256_DEFAULT                                                \
  "7d51cd6b48b521277f5caa4610a82126e315fa2be4df069823a8b1eeb5bd4a86"
#define PYTHON_SIZE_DEFAULT 5917224
#define HELPER_SHA256_DEFAULT                                                \
  "93ad5dbf86cfe9d70536cf53d08ae68de632b701de1b41e69387319c406a91bb"
#define HELPER_SIZE_DEFAULT 22954

#define AUDIT_OPERATION "audit"
#define SEAL_OPERATION "seal"
#define RECONCILE_OPERATION "reconcile"
#define SEAL_ACKNOWLEDGEMENT                                                 \
  "I confirm no VISTA authority publisher is running and acknowledge one "  \
  "irreversible seal of /data/vista-authorities from 0755 to 0555."
#define RECONCILE_ACKNOWLEDGEMENT                                            \
  "I acknowledge an audit-and-fsync-only reconciliation of the already "    \
  "sealed /data/vista-authorities directory."

#ifdef VISTA_PARENT_SEAL_LAUNCHER_TESTING
#ifndef VISTA_PARENT_SEAL_TEST_ROOT
#error "VISTA_PARENT_SEAL_TEST_ROOT is required in testing mode"
#endif
#ifndef VISTA_PARENT_SEAL_TEST_REQUIRED_EUID
#error "VISTA_PARENT_SEAL_TEST_REQUIRED_EUID is required in testing mode"
#endif
#ifndef VISTA_PARENT_SEAL_TEST_REQUIRED_EGID
#error "VISTA_PARENT_SEAL_TEST_REQUIRED_EGID is required in testing mode"
#endif
#ifndef VISTA_PARENT_SEAL_TEST_OWNER_UID
#error "VISTA_PARENT_SEAL_TEST_OWNER_UID is required in testing mode"
#endif
#ifndef VISTA_PARENT_SEAL_TEST_OWNER_GID
#error "VISTA_PARENT_SEAL_TEST_OWNER_GID is required in testing mode"
#endif
#ifndef VISTA_PARENT_SEAL_TEST_HELPER_SHA256
#error "VISTA_PARENT_SEAL_TEST_HELPER_SHA256 is required in testing mode"
#endif
#ifndef VISTA_PARENT_SEAL_TEST_HELPER_SIZE
#error "VISTA_PARENT_SEAL_TEST_HELPER_SIZE is required in testing mode"
#endif
#define INSTALLED_ROOT VISTA_PARENT_SEAL_TEST_ROOT
#define REQUIRED_EUID ((uid_t)VISTA_PARENT_SEAL_TEST_REQUIRED_EUID)
#define REQUIRED_EGID ((gid_t)VISTA_PARENT_SEAL_TEST_REQUIRED_EGID)
#define AUTHORITY_UID ((uid_t)VISTA_PARENT_SEAL_TEST_OWNER_UID)
#define AUTHORITY_GID ((gid_t)VISTA_PARENT_SEAL_TEST_OWNER_GID)
#define HELPER_SHA256 VISTA_PARENT_SEAL_TEST_HELPER_SHA256
#define HELPER_SIZE VISTA_PARENT_SEAL_TEST_HELPER_SIZE
#else
#define INSTALLED_ROOT INSTALLED_ROOT_DEFAULT
#define REQUIRED_EUID ((uid_t)0)
#define REQUIRED_EGID ((gid_t)0)
#define AUTHORITY_UID ((uid_t)0)
#define AUTHORITY_GID ((gid_t)0)
#define HELPER_SHA256 HELPER_SHA256_DEFAULT
#define HELPER_SIZE HELPER_SIZE_DEFAULT
#endif

#define SELF_PATH INSTALLED_ROOT "/" LAUNCHER_NAME
#define HELPER_PATH INSTALLED_ROOT "/" HELPER_NAME
#define PYTHON_SHA256 PYTHON_SHA256_DEFAULT
#define PYTHON_SIZE PYTHON_SIZE_DEFAULT

_Static_assert(sizeof(PYTHON_SHA256) == 65,
               "Python SHA-256 must contain 64 bytes");
_Static_assert(sizeof(HELPER_SHA256) == 65,
               "helper SHA-256 must contain 64 bytes");
_Static_assert(PYTHON_SIZE > 0, "Python size must be positive");
_Static_assert(HELPER_SIZE > 0, "helper size must be positive");

enum {
  FAILURE_EXIT = 126,
  INSTALLED_ROOT_MODE = 0555,
  LAUNCHER_MODE = 0555,
  HELPER_MODE = 0500,
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

static int verify_pin(int descriptor, const fixed_pin *pin) {
  static const char hexadecimal[] = "0123456789abcdef";
  unsigned char buffer[64 * 1024];
  unsigned char digest[32];
  char actual[65];
  sha256_context context;
  struct stat metadata;
  off_t total = 0;
  ssize_t observed;
  int index;

  if (pin->size_bytes <= 0 || pin->size_bytes > MAX_PINNED_BYTES ||
      !valid_sha256(pin->sha256) || fstat(descriptor, &metadata) != 0 ||
      !S_ISREG(metadata.st_mode) || metadata.st_size != pin->size_bytes ||
      lseek(descriptor, 0, SEEK_SET) < 0) {
    return -1;
  }
  initialize(&context);
  while (total < pin->size_bytes) {
    size_t remaining = (size_t)(pin->size_bytes - total);
    size_t requested = remaining < sizeof(buffer) ? remaining : sizeof(buffer);
    observed = read(descriptor, buffer, requested);
    if (observed <= 0) {
      return -1;
    }
    total += observed;
    update(&context, buffer, (size_t)observed);
  }
  observed = read(descriptor, buffer, 1);
  if (observed != 0 || lseek(descriptor, 0, SEEK_SET) < 0) {
    return -1;
  }
  finalize(&context, digest);
  for (index = 0; index < 32; ++index) {
    actual[2 * index] = hexadecimal[digest[index] >> 4];
    actual[2 * index + 1] = hexadecimal[digest[index] & 15];
  }
  actual[64] = '\0';
  return strcmp(actual, pin->sha256) == 0 ? 0 : -1;
}

static int fail(const char *message) {
  (void)!write(STDERR_FILENO, message, strlen(message));
  (void)!write(STDERR_FILENO, "\n", 1);
  return FAILURE_EXIT;
}

static int same_identity(const struct stat *left, const struct stat *right) {
  return left->st_dev == right->st_dev && left->st_ino == right->st_ino &&
         left->st_mode == right->st_mode &&
         left->st_uid == right->st_uid && left->st_gid == right->st_gid &&
         left->st_nlink == right->st_nlink &&
         left->st_size == right->st_size &&
         left->st_mtim.tv_sec == right->st_mtim.tv_sec &&
         left->st_mtim.tv_nsec == right->st_mtim.tv_nsec &&
         left->st_ctim.tv_sec == right->st_ctim.tv_sec &&
         left->st_ctim.tv_nsec == right->st_ctim.tv_nsec;
}

static int verify_directory(int descriptor, mode_t mode, uid_t uid, gid_t gid,
                            int exact_links, struct stat *result) {
  struct stat metadata;
  if (fstat(descriptor, &metadata) != 0 || !S_ISDIR(metadata.st_mode) ||
      metadata.st_uid != uid || metadata.st_gid != gid ||
      (metadata.st_mode & 07777) != mode ||
      (exact_links >= 0 && metadata.st_nlink != (nlink_t)exact_links)) {
    return -1;
  }
  if (result != NULL) {
    *result = metadata;
  }
  return 0;
}

static int verify_regular(int descriptor, mode_t mode, uid_t uid, gid_t gid,
                          struct stat *result) {
  struct stat metadata;
  if (fstat(descriptor, &metadata) != 0 || !S_ISREG(metadata.st_mode) ||
      metadata.st_nlink != 1 || metadata.st_uid != uid ||
      metadata.st_gid != gid || (metadata.st_mode & 07777) != mode) {
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
    int is_last;
    int next;
    while (cursor < length && copy[cursor] != '/') {
      ++cursor;
    }
    component_length = cursor - start;
    is_last = cursor == length;
    if (component_length == 0 || component_length > NAME_MAX ||
        (component_length == 1 && copy[start] == '.') ||
        (component_length == 2 && copy[start] == '.' &&
         copy[start + 1] == '.')) {
      (void)close(current);
      return -1;
    }
    copy[start + component_length] = '\0';
    if (is_last) {
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
      verify_regular(descriptor, mode, uid, gid, metadata) != 0) {
    if (descriptor >= 0) {
      (void)close(descriptor);
    }
    return -1;
  }
  return descriptor;
}

static int exact_inventory(int root_descriptor) {
  const char *names[2] = {LAUNCHER_NAME, HELPER_NAME};
  unsigned char seen[2] = {0, 0};
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
    for (index = 0; index < 2; ++index) {
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
  if (errno != 0 || closedir(stream) != 0 || observed != 2) {
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

static int production_ancestors_are_exact(void) {
#ifdef VISTA_PARENT_SEAL_LAUNCHER_TESTING
  return 0;
#else
  struct stat root_metadata;
  struct stat private_metadata;
  int root_descriptor =
      open("/", O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
  int private_descriptor;
  if (root_descriptor < 0 ||
      verify_directory(root_descriptor, 0755, 0, 0, -1, &root_metadata) != 0) {
    return -1;
  }
  private_descriptor = openat(root_descriptor, "root",
                              O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
  (void)close(root_descriptor);
  if (private_descriptor < 0 ||
      verify_directory(private_descriptor, 0700, 0, 0, -1,
                       &private_metadata) != 0) {
    if (private_descriptor >= 0) {
      (void)close(private_descriptor);
    }
    return -1;
  }
  (void)close(private_descriptor);
  return 0;
#endif
}

int main(int argc, char **argv) {
  const char *operation;
  const char *acknowledgement = NULL;
  fixed_pin python_pin = {PYTHON_SHA256, (off_t)PYTHON_SIZE};
  fixed_pin helper_pin = {HELPER_SHA256, (off_t)HELPER_SIZE};
  struct stat root_metadata;
  struct stat self_metadata;
  struct stat live_self_metadata;
  struct stat helper_metadata;
  struct stat python_metadata;
  struct stat final_root_metadata;
  struct stat final_self_metadata;
  struct stat final_helper_metadata;
  int parent;
  char root_name[NAME_MAX + 1];
  int root_descriptor;
  int self_descriptor;
  int live_self_descriptor;
  int helper_descriptor;
  int python_descriptor;
  int final_root_descriptor;
  int final_self_descriptor;
  int final_helper_descriptor;
  char helper_fd_path[64];
  char launcher_fd_text[32];
  int helper_fd_length;
  int launcher_fd_length;

  if (argc == 2 && strcmp(argv[1], AUDIT_OPERATION) == 0) {
    operation = AUDIT_OPERATION;
  } else if (argc == 3 && strcmp(argv[1], SEAL_OPERATION) == 0) {
    operation = SEAL_OPERATION;
    acknowledgement = SEAL_ACKNOWLEDGEMENT;
  } else if (argc == 3 && strcmp(argv[1], RECONCILE_OPERATION) == 0) {
    operation = RECONCILE_OPERATION;
    acknowledgement = RECONCILE_ACKNOWLEDGEMENT;
  } else {
    return fail("PARENT_SEAL_LAUNCHER: closed operation/argc required");
  }
  if (acknowledgement != NULL && strcmp(argv[2], acknowledgement) != 0) {
    return fail("PARENT_SEAL_LAUNCHER: acknowledgement differs");
  }
  if (geteuid() != REQUIRED_EUID || getegid() != REQUIRED_EGID) {
    return fail("PARENT_SEAL_LAUNCHER: root EUID and EGID required");
  }
  if (!valid_sha256(PYTHON_SHA256) || !valid_sha256(HELPER_SHA256) ||
      production_ancestors_are_exact() != 0 ||
      open_parent_nofollow(INSTALLED_ROOT, &parent, root_name) != 0) {
    return fail("PARENT_SEAL_LAUNCHER: fixed ancestor contract differs");
  }
  root_descriptor = openat(parent, root_name,
                           O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
  (void)close(parent);
  if (root_descriptor < 0 ||
      verify_directory(root_descriptor, INSTALLED_ROOT_MODE, AUTHORITY_UID,
                       AUTHORITY_GID, 2, &root_metadata) != 0 ||
      exact_inventory(root_descriptor) != 0) {
    return fail("PARENT_SEAL_LAUNCHER: installed root inventory differs");
  }
  self_descriptor = openat(root_descriptor, LAUNCHER_NAME,
                           O_RDONLY | O_NONBLOCK | O_NOFOLLOW | O_CLOEXEC);
  helper_descriptor = openat(root_descriptor, HELPER_NAME,
                             O_RDONLY | O_NONBLOCK | O_NOFOLLOW | O_CLOEXEC);
  if (self_descriptor < 0 || helper_descriptor < 0 ||
      verify_regular(self_descriptor, LAUNCHER_MODE, AUTHORITY_UID,
                     AUTHORITY_GID, &self_metadata) != 0 ||
      verify_regular(helper_descriptor, HELPER_MODE, AUTHORITY_UID,
                     AUTHORITY_GID, &helper_metadata) != 0 ||
      verify_pin(helper_descriptor, &helper_pin) != 0) {
    return fail("PARENT_SEAL_LAUNCHER: installed files differ");
  }
  live_self_descriptor =
      open("/proc/self/exe", O_RDONLY | O_NONBLOCK | O_CLOEXEC);
  if (live_self_descriptor < 0 ||
      verify_regular(live_self_descriptor, LAUNCHER_MODE, AUTHORITY_UID,
                     AUTHORITY_GID, &live_self_metadata) != 0 ||
      !same_identity(&self_metadata, &live_self_metadata)) {
    return fail("PARENT_SEAL_LAUNCHER: live self identity differs");
  }
  python_descriptor = open_regular_path(PYTHON_PATH, PYTHON_MODE, 0, 0,
                                        &python_metadata);
  if (python_descriptor < 0 || verify_pin(python_descriptor, &python_pin) != 0) {
    return fail("PARENT_SEAL_LAUNCHER: pinned Python differs");
  }

  if (verify_directory(root_descriptor, INSTALLED_ROOT_MODE, AUTHORITY_UID,
                       AUTHORITY_GID, 2, NULL) != 0 ||
      exact_inventory(root_descriptor) != 0 ||
      verify_regular(self_descriptor, LAUNCHER_MODE, AUTHORITY_UID,
                     AUTHORITY_GID, NULL) != 0 ||
      verify_regular(helper_descriptor, HELPER_MODE, AUTHORITY_UID,
                     AUTHORITY_GID, NULL) != 0 ||
      verify_pin(helper_descriptor, &helper_pin) != 0 ||
      verify_regular(python_descriptor, PYTHON_MODE, 0, 0, NULL) != 0 ||
      verify_pin(python_descriptor, &python_pin) != 0) {
    return fail("PARENT_SEAL_LAUNCHER: held input identity drifted");
  }
  if (open_parent_nofollow(INSTALLED_ROOT, &parent, root_name) != 0) {
    return fail("PARENT_SEAL_LAUNCHER: installed root path drifted");
  }
  final_root_descriptor = openat(
      parent, root_name, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
  (void)close(parent);
  if (final_root_descriptor < 0 ||
      verify_directory(final_root_descriptor, INSTALLED_ROOT_MODE,
                       AUTHORITY_UID, AUTHORITY_GID, 2,
                       &final_root_metadata) != 0 ||
      !same_identity(&root_metadata, &final_root_metadata) ||
      exact_inventory(final_root_descriptor) != 0) {
    return fail("PARENT_SEAL_LAUNCHER: installed root path drifted");
  }
  final_self_descriptor = openat(
      final_root_descriptor, LAUNCHER_NAME,
      O_RDONLY | O_NONBLOCK | O_NOFOLLOW | O_CLOEXEC);
  final_helper_descriptor = openat(
      final_root_descriptor, HELPER_NAME,
      O_RDONLY | O_NONBLOCK | O_NOFOLLOW | O_CLOEXEC);
  if (final_self_descriptor < 0 || final_helper_descriptor < 0 ||
      verify_regular(final_self_descriptor, LAUNCHER_MODE, AUTHORITY_UID,
                     AUTHORITY_GID, &final_self_metadata) != 0 ||
      verify_regular(final_helper_descriptor, HELPER_MODE, AUTHORITY_UID,
                     AUTHORITY_GID, &final_helper_metadata) != 0 ||
      !same_identity(&self_metadata, &final_self_metadata) ||
      !same_identity(&helper_metadata, &final_helper_metadata) ||
      verify_pin(final_helper_descriptor, &helper_pin) != 0 ||
      verify_regular(live_self_descriptor, LAUNCHER_MODE, AUTHORITY_UID,
                     AUTHORITY_GID, NULL) != 0 ||
      !same_identity(&self_metadata, &live_self_metadata) ||
      clear_close_on_exec(helper_descriptor) != 0 ||
      clear_close_on_exec(self_descriptor) != 0) {
    return fail("PARENT_SEAL_LAUNCHER: final authority identity drifted");
  }

  helper_fd_length = snprintf(helper_fd_path, sizeof(helper_fd_path),
                              "/proc/self/fd/%d", helper_descriptor);
  launcher_fd_length = snprintf(launcher_fd_text, sizeof(launcher_fd_text),
                                "%d", self_descriptor);
  if (helper_fd_length < 0 ||
      (size_t)helper_fd_length >= sizeof(helper_fd_path) ||
      launcher_fd_length < 0 ||
      (size_t)launcher_fd_length >= sizeof(launcher_fd_text)) {
    return fail("PARENT_SEAL_LAUNCHER: helper descriptor formatting failed");
  }
  {
    char *const audit_argv[] = {
        PYTHON_PATH,
        "-I",
        "-B",
        helper_fd_path,
        (char *)operation,
        "--parent-seal-launcher-fd",
        launcher_fd_text,
        NULL,
    };
    char *const acknowledged_argv[] = {
        PYTHON_PATH,
        "-I",
        "-B",
        helper_fd_path,
        (char *)operation,
        "--parent-seal-launcher-fd",
        launcher_fd_text,
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
    char *const *child_argv = acknowledgement == NULL ? audit_argv
                                                       : acknowledged_argv;
    (void)syscall(SYS_execveat, python_descriptor, "", child_argv, child_env,
                  AT_EMPTY_PATH);
  }
  return fail("PARENT_SEAL_LAUNCHER: held-Python execveat failed");
}
