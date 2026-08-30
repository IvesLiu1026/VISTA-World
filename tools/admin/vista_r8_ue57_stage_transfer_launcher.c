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
 * Initial-core trust entry for transferring the four reviewed one-shot stage
 * installers into independent root authorities.  The caller supplies only a
 * closed operation, closed stage key, external SHA-256/size, and the exact
 * stage/action acknowledgement.  Candidate and final paths are compiled.
 */
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

_Static_assert(sizeof(EXPECTED_PYTHON_SHA256) == 65,
               "EXPECTED_PYTHON_SHA256 must contain 64 bytes");
_Static_assert(sizeof(EXPECTED_HELPER_SHA256) == 65,
               "EXPECTED_HELPER_SHA256 must contain 64 bytes");
_Static_assert(EXPECTED_PYTHON_SIZE > 0,
               "EXPECTED_PYTHON_SIZE must be positive");
_Static_assert(EXPECTED_HELPER_SIZE > 0,
               "EXPECTED_HELPER_SIZE must be positive");

#define CORE_ROOT_DEFAULT "/root/vista-r8-ue57-authority-r2"
#define SELF_NAME "transfer-r8-ue57-stage-installer"
#define HELPER_NAME "vista_r8_ue57_authority_admin.py"
#define ENGINE_WRAPPER_NAME "provision_vista_r8_ue57_engine.sh"
#define ENGINE_PIN_NAME "engine-source-pin.json"
#define PYTHON_PATH "/usr/bin/python3.10"
#define INSTALLER_NAME "install-reconcile-r8-ue57-stage"
#define RECEIPT_NAME "receipt.json"
#define INSTALL_OPERATION "install-stage-installer-authority"
#define RECONCILE_OPERATION "reconcile-stage-installer-authority"

#define REVIEW_PARENT_DEFAULT                                               \
  "/data/sysx/vista-world/runs/vista-action-world-r1"
#define FINAL_PARENT_DEFAULT "/root/vista-r8-ue57-stage-installers-r1"

#ifdef VISTA_R8_STAGE_TRANSFER_TESTING
#ifndef VISTA_R8_TRANSFER_TEST_CORE_ROOT
#error "VISTA_R8_TRANSFER_TEST_CORE_ROOT is required in testing mode"
#endif
#ifndef VISTA_R8_TRANSFER_TEST_REVIEW_PARENT
#error "VISTA_R8_TRANSFER_TEST_REVIEW_PARENT is required in testing mode"
#endif
#ifndef VISTA_R8_TRANSFER_TEST_FINAL_PARENT
#error "VISTA_R8_TRANSFER_TEST_FINAL_PARENT is required in testing mode"
#endif
#ifndef VISTA_R8_TRANSFER_TEST_REQUIRED_EUID
#error "VISTA_R8_TRANSFER_TEST_REQUIRED_EUID is required in testing mode"
#endif
#ifndef VISTA_R8_TRANSFER_TEST_REQUIRED_EGID
#error "VISTA_R8_TRANSFER_TEST_REQUIRED_EGID is required in testing mode"
#endif
#ifndef VISTA_R8_TRANSFER_TEST_CORE_UID
#error "VISTA_R8_TRANSFER_TEST_CORE_UID is required in testing mode"
#endif
#ifndef VISTA_R8_TRANSFER_TEST_CORE_GID
#error "VISTA_R8_TRANSFER_TEST_CORE_GID is required in testing mode"
#endif
#ifndef VISTA_R8_TRANSFER_TEST_REVIEW_UID
#error "VISTA_R8_TRANSFER_TEST_REVIEW_UID is required in testing mode"
#endif
#ifndef VISTA_R8_TRANSFER_TEST_REVIEW_GID
#error "VISTA_R8_TRANSFER_TEST_REVIEW_GID is required in testing mode"
#endif
#define CORE_ROOT VISTA_R8_TRANSFER_TEST_CORE_ROOT
#define REVIEW_PARENT VISTA_R8_TRANSFER_TEST_REVIEW_PARENT
#define FINAL_PARENT VISTA_R8_TRANSFER_TEST_FINAL_PARENT
#define REQUIRED_EUID ((uid_t)VISTA_R8_TRANSFER_TEST_REQUIRED_EUID)
#define REQUIRED_EGID ((gid_t)VISTA_R8_TRANSFER_TEST_REQUIRED_EGID)
#define CORE_UID ((uid_t)VISTA_R8_TRANSFER_TEST_CORE_UID)
#define CORE_GID ((gid_t)VISTA_R8_TRANSFER_TEST_CORE_GID)
#define REVIEW_UID ((uid_t)VISTA_R8_TRANSFER_TEST_REVIEW_UID)
#define REVIEW_GID ((gid_t)VISTA_R8_TRANSFER_TEST_REVIEW_GID)
#else
#define CORE_ROOT CORE_ROOT_DEFAULT
#define REVIEW_PARENT REVIEW_PARENT_DEFAULT
#define FINAL_PARENT FINAL_PARENT_DEFAULT
#define REQUIRED_EUID ((uid_t)0)
#define REQUIRED_EGID ((gid_t)0)
#define CORE_UID ((uid_t)0)
#define CORE_GID ((gid_t)0)
#define REVIEW_UID ((uid_t)1000021)
#define REVIEW_GID ((gid_t)1000001)
#endif

#define SELF_PATH CORE_ROOT "/" SELF_NAME
#define HELPER_PATH CORE_ROOT "/" HELPER_NAME

enum {
  FAILURE_EXIT = 126,
  CORE_ROOT_MODE = 0555,
  SELF_MODE = 0555,
  HELPER_MODE = 0500,
  ENGINE_WRAPPER_MODE = 0500,
  ENGINE_PIN_MODE = 0444,
  LOCK_MODE = 0600,
  REVIEW_ROOT_MODE = 0555,
  REVIEW_INSTALLER_MODE = 0555,
  FINAL_ROOT_MODE = 0555,
  FINAL_INSTALLER_MODE = 0555,
  FINAL_RECEIPT_MODE = 0444,
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
  char sha256[65];
  off_t size_bytes;
} file_pin;

typedef struct {
  const char *name;
  mode_t mode;
  int exact_zero_size;
  int descriptor;
  struct stat metadata;
} core_file;

typedef struct {
  const char *key;
  const char *candidate_root;
  const char *final_root;
  const char *install_acknowledgement;
  const char *reconcile_acknowledgement;
} stage_contract;

#define RUNTIME_INPUT_INSTALL_ACK                                           \
  "I acknowledge one fresh root transfer of the externally reviewed VISTA " \
  "R8 UE 5.7 runtime-input one-shot stage installer."
#define RUNTIME_INPUT_RECONCILE_ACK                                         \
  "I acknowledge reconciliation of the externally reviewed VISTA R8 UE "   \
  "5.7 runtime-input one-shot stage installer without republishing or "     \
  "deleting it."
#define RUNTIME_PLAN_INSTALL_ACK                                            \
  "I acknowledge one fresh root transfer of the externally reviewed VISTA " \
  "R8 UE 5.7 runtime-plan one-shot stage installer."
#define RUNTIME_PLAN_RECONCILE_ACK                                          \
  "I acknowledge reconciliation of the externally reviewed VISTA R8 UE "   \
  "5.7 runtime-plan one-shot stage installer without republishing or "      \
  "deleting it."
#define BUNDLE_INPUT_INSTALL_ACK                                            \
  "I acknowledge one fresh root transfer of the externally reviewed VISTA " \
  "R8 UE 5.7 bundle-input one-shot stage installer."
#define BUNDLE_INPUT_RECONCILE_ACK                                          \
  "I acknowledge reconciliation of the externally reviewed VISTA R8 UE "   \
  "5.7 bundle-input one-shot stage installer without republishing or "      \
  "deleting it."
#define BUNDLE_PLAN_INSTALL_ACK                                             \
  "I acknowledge one fresh root transfer of the externally reviewed VISTA " \
  "R8 UE 5.7 bundle-plan one-shot stage installer."
#define BUNDLE_PLAN_RECONCILE_ACK                                           \
  "I acknowledge reconciliation of the externally reviewed VISTA R8 UE "   \
  "5.7 bundle-plan one-shot stage installer without republishing or "       \
  "deleting it."

#ifdef VISTA_R8_STAGE_TRANSFER_TESTING
#define RUNTIME_INPUT_CANDIDATE REVIEW_PARENT "/runtime-input"
#define RUNTIME_PLAN_CANDIDATE REVIEW_PARENT "/runtime-plan"
#define BUNDLE_INPUT_CANDIDATE REVIEW_PARENT "/bundle-input"
#define BUNDLE_PLAN_CANDIDATE REVIEW_PARENT "/bundle-plan"
#else
#define RUNTIME_INPUT_CANDIDATE                                             \
  REVIEW_PARENT "/vista-r8-ue57-runtime-input-stage-installer-review-"      \
                "candidate-20260830a"
#define RUNTIME_PLAN_CANDIDATE                                              \
  REVIEW_PARENT "/vista-r8-ue57-runtime-plan-stage-installer-review-"       \
                "candidate-20260830a"
#define BUNDLE_INPUT_CANDIDATE                                              \
  REVIEW_PARENT "/vista-r8-ue57-bundle-input-stage-installer-review-"       \
                "candidate-20260830a"
#define BUNDLE_PLAN_CANDIDATE                                               \
  REVIEW_PARENT "/vista-r8-ue57-bundle-plan-stage-installer-review-"        \
                "candidate-20260830a"
#endif

static const stage_contract stages[4] = {
    {"runtime-input", RUNTIME_INPUT_CANDIDATE,
     FINAL_PARENT "/runtime-input", RUNTIME_INPUT_INSTALL_ACK,
     RUNTIME_INPUT_RECONCILE_ACK},
    {"runtime-plan", RUNTIME_PLAN_CANDIDATE,
     FINAL_PARENT "/runtime-plan", RUNTIME_PLAN_INSTALL_ACK,
     RUNTIME_PLAN_RECONCILE_ACK},
    {"bundle-input", BUNDLE_INPUT_CANDIDATE,
     FINAL_PARENT "/bundle-input", BUNDLE_INPUT_INSTALL_ACK,
     BUNDLE_INPUT_RECONCILE_ACK},
    {"bundle-plan", BUNDLE_PLAN_CANDIDATE,
     FINAL_PARENT "/bundle-plan", BUNDLE_PLAN_INSTALL_ACK,
     BUNDLE_PLAN_RECONCILE_ACK},
};

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

static int verify_pin(int descriptor, const file_pin *pin) {
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
                            int links, struct stat *result) {
  struct stat metadata;
  if (fstat(descriptor, &metadata) != 0 || !S_ISDIR(metadata.st_mode) ||
      metadata.st_uid != uid || metadata.st_gid != gid ||
      (metadata.st_mode & 07777) != mode ||
      (links >= 0 && metadata.st_nlink != (nlink_t)links)) {
    return -1;
  }
  if (result != NULL) {
    *result = metadata;
  }
  return 0;
}

static int verify_regular(int descriptor, mode_t mode, uid_t uid, gid_t gid,
                          int exact_zero_size, struct stat *result) {
  struct stat metadata;
  if (fstat(descriptor, &metadata) != 0 || !S_ISREG(metadata.st_mode) ||
      metadata.st_nlink != 1 || metadata.st_uid != uid ||
      metadata.st_gid != gid || (metadata.st_mode & 07777) != mode ||
      (exact_zero_size && metadata.st_size != 0)) {
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

static int open_directory_path(const char *path, mode_t mode, uid_t uid,
                               gid_t gid, int links, struct stat *metadata) {
  char name[NAME_MAX + 1];
  int parent;
  int descriptor;
  if (open_parent_nofollow(path, &parent, name) != 0) {
    return -1;
  }
  descriptor = openat(parent, name,
                      O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
  (void)close(parent);
  if (descriptor < 0 ||
      verify_directory(descriptor, mode, uid, gid, links, metadata) != 0) {
    if (descriptor >= 0) {
      (void)close(descriptor);
    }
    return -1;
  }
  return descriptor;
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
      verify_regular(descriptor, mode, uid, gid, 0, metadata) != 0) {
    if (descriptor >= 0) {
      (void)close(descriptor);
    }
    return -1;
  }
  return descriptor;
}

static int exact_inventory(int directory, const char *const *names,
                           size_t count) {
  unsigned char seen[8] = {0};
  int duplicate = openat(directory, ".",
                         O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
  DIR *stream;
  struct dirent *entry;
  size_t observed = 0;
  if (count > sizeof(seen) || duplicate < 0) {
    return -1;
  }
  stream = fdopendir(duplicate);
  if (stream == NULL) {
    (void)close(duplicate);
    return -1;
  }
  errno = 0;
  while ((entry = readdir(stream)) != NULL) {
    size_t index;
    int matched = 0;
    if (strcmp(entry->d_name, ".") == 0 || strcmp(entry->d_name, "..") == 0) {
      continue;
    }
    for (index = 0; index < count; ++index) {
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
  if (errno != 0 || closedir(stream) != 0 || observed != count) {
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

static int parse_size(const char *value, off_t *result) {
  uintmax_t parsed = 0;
  const char *cursor = value;
  if (*cursor < '1' || *cursor > '9') {
    return -1;
  }
  while (*cursor >= '0' && *cursor <= '9') {
    unsigned int digit = (unsigned int)(*cursor - '0');
    if (parsed > ((uintmax_t)INT64_MAX - digit) / 10u) {
      return -1;
    }
    parsed = parsed * 10u + digit;
    ++cursor;
  }
  if (*cursor != '\0' || parsed > MAX_PINNED_BYTES) {
    return -1;
  }
  *result = (off_t)parsed;
  return 0;
}

static const stage_contract *find_stage(const char *key) {
  size_t index;
  for (index = 0; index < 4; ++index) {
    if (strcmp(key, stages[index].key) == 0) {
      return &stages[index];
    }
  }
  return NULL;
}

static int open_core(core_file files[8], int *root_result,
                     struct stat *root_metadata) {
  static const char *const names[8] = {
      HELPER_NAME,
      ENGINE_WRAPPER_NAME,
      SELF_NAME,
      ENGINE_PIN_NAME,
      ".engine.lock",
      ".runtime.lock",
      ".bundle.lock",
      ".executor.lock",
  };
  size_t index;
  int root = open_directory_path(CORE_ROOT, CORE_ROOT_MODE, CORE_UID, CORE_GID,
                                 2, root_metadata);
  if (root < 0 || exact_inventory(root, names, 8) != 0) {
    return -1;
  }
  files[0] = (core_file){names[0], HELPER_MODE, 0, -1, {0}};
  files[1] = (core_file){names[1], ENGINE_WRAPPER_MODE, 0, -1, {0}};
  files[2] = (core_file){names[2], SELF_MODE, 0, -1, {0}};
  files[3] = (core_file){names[3], ENGINE_PIN_MODE, 0, -1, {0}};
  files[4] = (core_file){names[4], LOCK_MODE, 1, -1, {0}};
  files[5] = (core_file){names[5], LOCK_MODE, 1, -1, {0}};
  files[6] = (core_file){names[6], LOCK_MODE, 1, -1, {0}};
  files[7] = (core_file){names[7], LOCK_MODE, 1, -1, {0}};
  for (index = 0; index < 8; ++index) {
    files[index].descriptor =
        openat(root, files[index].name,
               O_RDONLY | O_NONBLOCK | O_NOFOLLOW | O_CLOEXEC);
    if (files[index].descriptor < 0 ||
        verify_regular(files[index].descriptor, files[index].mode, CORE_UID,
                       CORE_GID, files[index].exact_zero_size,
                       &files[index].metadata) != 0) {
      return -1;
    }
  }
  *root_result = root;
  return 0;
}

static int revalidate_core(int root, const struct stat *root_metadata,
                           core_file files[8]) {
  static const char *const names[8] = {
      HELPER_NAME, ENGINE_WRAPPER_NAME, SELF_NAME, ENGINE_PIN_NAME,
      ".engine.lock", ".runtime.lock", ".bundle.lock", ".executor.lock",
  };
  struct stat current_root;
  struct stat reopened_root_metadata;
  int reopened_root;
  size_t index;
  if (verify_directory(root, CORE_ROOT_MODE, CORE_UID, CORE_GID, 2,
                       &current_root) != 0 ||
      !same_identity(root_metadata, &current_root) ||
      exact_inventory(root, names, 8) != 0) {
    return -1;
  }
  reopened_root = open_directory_path(CORE_ROOT, CORE_ROOT_MODE, CORE_UID,
                                      CORE_GID, 2, &reopened_root_metadata);
  if (reopened_root < 0 ||
      !same_identity(root_metadata, &reopened_root_metadata) ||
      exact_inventory(reopened_root, names, 8) != 0) {
    return -1;
  }
  for (index = 0; index < 8; ++index) {
    struct stat current;
    struct stat reopened;
    int descriptor;
    if (verify_regular(files[index].descriptor, files[index].mode, CORE_UID,
                       CORE_GID, files[index].exact_zero_size, &current) != 0 ||
        !same_identity(&files[index].metadata, &current)) {
      return -1;
    }
    descriptor = openat(reopened_root, files[index].name,
                        O_RDONLY | O_NONBLOCK | O_NOFOLLOW | O_CLOEXEC);
    if (descriptor < 0 ||
        verify_regular(descriptor, files[index].mode, CORE_UID, CORE_GID,
                       files[index].exact_zero_size, &reopened) != 0 ||
        !same_identity(&files[index].metadata, &reopened)) {
      return -1;
    }
    (void)close(descriptor);
  }
  (void)close(reopened_root);
  return 0;
}

int main(int argc, char **argv) {
  const stage_contract *stage;
  const char *operation;
  const char *acknowledgement;
  int is_reconcile;
  file_pin external_pin;
  file_pin python_pin = {EXPECTED_PYTHON_SHA256, (off_t)EXPECTED_PYTHON_SIZE};
  file_pin helper_pin = {EXPECTED_HELPER_SHA256, (off_t)EXPECTED_HELPER_SIZE};
  core_file core_files[8];
  struct stat core_metadata;
  struct stat live_self_metadata;
  struct stat python_metadata;
  struct stat transfer_root_metadata;
  struct stat transfer_installer_metadata;
  struct stat transfer_receipt_metadata;
  int core_root;
  int live_self;
  int python_descriptor;
  int transfer_root;
  int transfer_installer;
  int transfer_receipt = -1;
  int reopened_transfer_root;
  int reopened_transfer_installer;
  int reopened_transfer_receipt = -1;
  struct stat reopened_transfer_root_metadata;
  struct stat reopened_transfer_installer_metadata;
  struct stat reopened_transfer_receipt_metadata;
  char helper_fd_path[64];
  char self_fd_text[32];
  int helper_fd_length;
  int self_fd_length;
  static const char *const candidate_names[1] = {INSTALLER_NAME};
  static const char *const final_names[2] = {INSTALLER_NAME, RECEIPT_NAME};

  if (argc != 6) {
    return fail("R8_STAGE_TRANSFER: exact operation/stage/pin/ack required");
  }
  if (strcmp(argv[1], INSTALL_OPERATION) == 0) {
    operation = INSTALL_OPERATION;
    is_reconcile = 0;
  } else if (strcmp(argv[1], RECONCILE_OPERATION) == 0) {
    operation = RECONCILE_OPERATION;
    is_reconcile = 1;
  } else {
    return fail("R8_STAGE_TRANSFER: operation differs");
  }
  stage = find_stage(argv[2]);
  if (stage == NULL) {
    return fail("R8_STAGE_TRANSFER: stage differs");
  }
  if (!valid_sha256(argv[3]) || parse_size(argv[4], &external_pin.size_bytes) != 0) {
    return fail("R8_STAGE_TRANSFER: external installer pin differs");
  }
  memcpy(external_pin.sha256, argv[3], 65);
  acknowledgement = is_reconcile ? stage->reconcile_acknowledgement
                                 : stage->install_acknowledgement;
  if (strcmp(argv[5], acknowledgement) != 0) {
    return fail("R8_STAGE_TRANSFER: acknowledgement differs");
  }
  if (geteuid() != REQUIRED_EUID || getegid() != REQUIRED_EGID) {
    return fail("R8_STAGE_TRANSFER: root EUID and EGID required");
  }
  if (!valid_sha256(EXPECTED_PYTHON_SHA256) ||
      !valid_sha256(EXPECTED_HELPER_SHA256) ||
      open_core(core_files, &core_root, &core_metadata) != 0 ||
      verify_pin(core_files[0].descriptor, &helper_pin) != 0) {
    return fail("R8_STAGE_TRANSFER: sealed core differs");
  }
  live_self = open("/proc/self/exe", O_RDONLY | O_NONBLOCK | O_CLOEXEC);
  if (live_self < 0 ||
      verify_regular(live_self, SELF_MODE, CORE_UID, CORE_GID, 0,
                     &live_self_metadata) != 0 ||
      !same_identity(&core_files[2].metadata, &live_self_metadata)) {
    return fail("R8_STAGE_TRANSFER: live self identity differs");
  }
  python_descriptor = open_regular_path(PYTHON_PATH, PYTHON_MODE, 0, 0,
                                        &python_metadata);
  if (python_descriptor < 0 || verify_pin(python_descriptor, &python_pin) != 0) {
    return fail("R8_STAGE_TRANSFER: pinned Python differs");
  }

  if (is_reconcile) {
    transfer_root = open_directory_path(
        stage->final_root, FINAL_ROOT_MODE, CORE_UID, CORE_GID, 2,
        &transfer_root_metadata);
    if (transfer_root < 0 || exact_inventory(transfer_root, final_names, 2) != 0) {
      return fail("R8_STAGE_TRANSFER: final installer authority differs");
    }
    transfer_installer = openat(
        transfer_root, INSTALLER_NAME,
        O_RDONLY | O_NONBLOCK | O_NOFOLLOW | O_CLOEXEC);
    transfer_receipt = openat(transfer_root, RECEIPT_NAME,
                              O_RDONLY | O_NONBLOCK | O_NOFOLLOW | O_CLOEXEC);
    if (transfer_installer < 0 || transfer_receipt < 0 ||
        verify_regular(transfer_installer, FINAL_INSTALLER_MODE, CORE_UID,
                       CORE_GID, 0, &transfer_installer_metadata) != 0 ||
        verify_regular(transfer_receipt, FINAL_RECEIPT_MODE, CORE_UID, CORE_GID,
                       0, &transfer_receipt_metadata) != 0 ||
        verify_pin(transfer_installer, &external_pin) != 0) {
      return fail("R8_STAGE_TRANSFER: final installer authority differs");
    }
  } else {
    transfer_root = open_directory_path(
        stage->candidate_root, REVIEW_ROOT_MODE, REVIEW_UID, REVIEW_GID, 2,
        &transfer_root_metadata);
    if (transfer_root < 0 ||
        exact_inventory(transfer_root, candidate_names, 1) != 0) {
      return fail("R8_STAGE_TRANSFER: reviewed installer candidate differs");
    }
    transfer_installer = openat(
        transfer_root, INSTALLER_NAME,
        O_RDONLY | O_NONBLOCK | O_NOFOLLOW | O_CLOEXEC);
    if (transfer_installer < 0 ||
        verify_regular(transfer_installer, REVIEW_INSTALLER_MODE, REVIEW_UID,
                       REVIEW_GID, 0, &transfer_installer_metadata) != 0 ||
        verify_pin(transfer_installer, &external_pin) != 0) {
      return fail("R8_STAGE_TRANSFER: reviewed installer candidate differs");
    }
  }

  reopened_transfer_root = open_directory_path(
      is_reconcile ? stage->final_root : stage->candidate_root,
      is_reconcile ? FINAL_ROOT_MODE : REVIEW_ROOT_MODE,
      is_reconcile ? CORE_UID : REVIEW_UID,
      is_reconcile ? CORE_GID : REVIEW_GID, 2,
      &reopened_transfer_root_metadata);
  if (reopened_transfer_root < 0 ||
      !same_identity(&transfer_root_metadata,
                     &reopened_transfer_root_metadata) ||
      exact_inventory(reopened_transfer_root,
                      is_reconcile ? final_names : candidate_names,
                      is_reconcile ? 2 : 1) != 0) {
    return fail("R8_STAGE_TRANSFER: fixed transfer path drifted");
  }
  reopened_transfer_installer = openat(
      reopened_transfer_root, INSTALLER_NAME,
      O_RDONLY | O_NONBLOCK | O_NOFOLLOW | O_CLOEXEC);
  if (reopened_transfer_installer < 0 ||
      verify_regular(reopened_transfer_installer,
                     is_reconcile ? FINAL_INSTALLER_MODE
                                  : REVIEW_INSTALLER_MODE,
                     is_reconcile ? CORE_UID : REVIEW_UID,
                     is_reconcile ? CORE_GID : REVIEW_GID, 0,
                     &reopened_transfer_installer_metadata) != 0 ||
      !same_identity(&transfer_installer_metadata,
                     &reopened_transfer_installer_metadata) ||
      verify_pin(reopened_transfer_installer, &external_pin) != 0) {
    return fail("R8_STAGE_TRANSFER: fixed installer path drifted");
  }
  if (is_reconcile) {
    reopened_transfer_receipt = openat(
        reopened_transfer_root, RECEIPT_NAME,
        O_RDONLY | O_NONBLOCK | O_NOFOLLOW | O_CLOEXEC);
    if (reopened_transfer_receipt < 0 ||
        verify_regular(reopened_transfer_receipt, FINAL_RECEIPT_MODE, CORE_UID,
                       CORE_GID, 0,
                       &reopened_transfer_receipt_metadata) != 0 ||
        !same_identity(&transfer_receipt_metadata,
                       &reopened_transfer_receipt_metadata)) {
      return fail("R8_STAGE_TRANSFER: fixed receipt path drifted");
    }
  }

  if (revalidate_core(core_root, &core_metadata, core_files) != 0 ||
      verify_pin(core_files[0].descriptor, &helper_pin) != 0 ||
      verify_regular(live_self, SELF_MODE, CORE_UID, CORE_GID, 0, NULL) != 0 ||
      verify_regular(python_descriptor, PYTHON_MODE, 0, 0, 0, NULL) != 0 ||
      verify_pin(python_descriptor, &python_pin) != 0 ||
      verify_directory(transfer_root,
                       is_reconcile ? FINAL_ROOT_MODE : REVIEW_ROOT_MODE,
                       is_reconcile ? CORE_UID : REVIEW_UID,
                       is_reconcile ? CORE_GID : REVIEW_GID, 2, NULL) != 0 ||
      exact_inventory(transfer_root,
                      is_reconcile ? final_names : candidate_names,
                      is_reconcile ? 2 : 1) != 0 ||
      verify_regular(transfer_installer,
                     is_reconcile ? FINAL_INSTALLER_MODE
                                  : REVIEW_INSTALLER_MODE,
                     is_reconcile ? CORE_UID : REVIEW_UID,
                     is_reconcile ? CORE_GID : REVIEW_GID, 0, NULL) != 0 ||
      verify_pin(transfer_installer, &external_pin) != 0 ||
      (is_reconcile &&
       verify_regular(transfer_receipt, FINAL_RECEIPT_MODE, CORE_UID, CORE_GID,
                      0, NULL) != 0) ||
      clear_close_on_exec(core_files[0].descriptor) != 0 ||
      clear_close_on_exec(core_files[2].descriptor) != 0) {
    return fail("R8_STAGE_TRANSFER: held authority identity drifted");
  }

  helper_fd_length = snprintf(helper_fd_path, sizeof(helper_fd_path),
                              "/proc/self/fd/%d", core_files[0].descriptor);
  self_fd_length = snprintf(self_fd_text, sizeof(self_fd_text), "%d",
                            core_files[2].descriptor);
  if (helper_fd_length < 0 ||
      (size_t)helper_fd_length >= sizeof(helper_fd_path) || self_fd_length < 0 ||
      (size_t)self_fd_length >= sizeof(self_fd_text)) {
    return fail("R8_STAGE_TRANSFER: inherited descriptor formatting failed");
  }
  {
    char *const child_argv[] = {
        PYTHON_PATH,
        "-I",
        "-B",
        helper_fd_path,
        (char *)operation,
        "--stage",
        (char *)stage->key,
        "--reviewed-installer-sha256",
        external_pin.sha256,
        "--reviewed-installer-size",
        argv[4],
        "--stage-transfer-launcher-fd",
        self_fd_text,
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
  return fail("R8_STAGE_TRANSFER: held-Python execveat failed");
}
