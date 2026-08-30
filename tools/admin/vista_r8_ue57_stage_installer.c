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
 * Frozen one-shot installer/reconciler for one sequential R8 UE 5.7 stage.
 *
 * Build exactly one of the four variants.  The resulting static ELF accepts
 * only: <compiled operation> <compiled acknowledgement>.  Paths and reviewed
 * byte pins are compile-time literals; no caller may supply a path or pin.
 *
 * A separately reviewed core helper copies each user-built installer into its
 * own root-owned authority.  That authority has exactly this executable and a
 * receipt.json.  The receipt binds the executable's own byte pin, avoiding a
 * self-hash compile cycle.  This process holds the installed executable and
 * passes that descriptor to the Python helper for a second receipt check
 * before the helper is allowed to write.
 */
#if (defined(VISTA_R8_STAGE_RUNTIME_INPUT) +                              \
     defined(VISTA_R8_STAGE_RUNTIME_PLAN) +                               \
     defined(VISTA_R8_STAGE_BUNDLE_INPUT) +                               \
     defined(VISTA_R8_STAGE_BUNDLE_PLAN)) != 1
#error "define exactly one VISTA R8 stage installer variant"
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

#if defined(VISTA_R8_STAGE_RUNTIME_INPUT) ||                              \
    defined(VISTA_R8_STAGE_BUNDLE_INPUT)
#ifndef EXPECTED_INPUT_PIN_SHA256
#error "EXPECTED_INPUT_PIN_SHA256 is required for input variants"
#endif
#ifndef EXPECTED_INPUT_PIN_SIZE
#error "EXPECTED_INPUT_PIN_SIZE is required for input variants"
#endif
#else
#ifndef EXPECTED_REVIEWED_PLAN_PIN_SHA256
#error "EXPECTED_REVIEWED_PLAN_PIN_SHA256 is required for plan variants"
#endif
#ifndef EXPECTED_REVIEWED_PLAN_PIN_SIZE
#error "EXPECTED_REVIEWED_PLAN_PIN_SIZE is required for plan variants"
#endif
#ifndef EXPECTED_ADMIN_LAUNCHER_SHA256
#error "EXPECTED_ADMIN_LAUNCHER_SHA256 is required for plan variants"
#endif
#ifndef EXPECTED_ADMIN_LAUNCHER_SIZE
#error "EXPECTED_ADMIN_LAUNCHER_SIZE is required for plan variants"
#endif
#endif

_Static_assert(EXPECTED_PYTHON_SIZE > 0,
               "EXPECTED_PYTHON_SIZE must be positive");
_Static_assert(EXPECTED_HELPER_SIZE > 0,
               "EXPECTED_HELPER_SIZE must be positive");
_Static_assert(sizeof(EXPECTED_PYTHON_SHA256) == 65,
               "EXPECTED_PYTHON_SHA256 must contain 64 bytes");
_Static_assert(sizeof(EXPECTED_HELPER_SHA256) == 65,
               "EXPECTED_HELPER_SHA256 must contain 64 bytes");

#if defined(VISTA_R8_STAGE_RUNTIME_INPUT) ||                              \
    defined(VISTA_R8_STAGE_BUNDLE_INPUT)
_Static_assert(EXPECTED_INPUT_PIN_SIZE > 0,
               "EXPECTED_INPUT_PIN_SIZE must be positive");
_Static_assert(sizeof(EXPECTED_INPUT_PIN_SHA256) == 65,
               "EXPECTED_INPUT_PIN_SHA256 must contain 64 bytes");
#else
_Static_assert(EXPECTED_REVIEWED_PLAN_PIN_SIZE > 0,
               "EXPECTED_REVIEWED_PLAN_PIN_SIZE must be positive");
_Static_assert(EXPECTED_ADMIN_LAUNCHER_SIZE > 0,
               "EXPECTED_ADMIN_LAUNCHER_SIZE must be positive");
_Static_assert(sizeof(EXPECTED_REVIEWED_PLAN_PIN_SHA256) == 65,
               "EXPECTED_REVIEWED_PLAN_PIN_SHA256 must contain 64 bytes");
_Static_assert(sizeof(EXPECTED_ADMIN_LAUNCHER_SHA256) == 65,
               "EXPECTED_ADMIN_LAUNCHER_SHA256 must contain 64 bytes");
#endif

#define STRINGIFY_INNER(value) #value
#define STRINGIFY(value) STRINGIFY_INNER(value)

#define INSTALLER_FILENAME "install-reconcile-r8-ue57-stage"
#define RECEIPT_FILENAME "receipt.json"
#define PYTHON_PATH_DEFAULT "/usr/bin/python3.10"
#define CORE_HELPER_PATH_DEFAULT                                             \
  "/root/vista-r8-ue57-authority-r2/vista_r8_ue57_authority_admin.py"

#if defined(VISTA_R8_STAGE_RUNTIME_INPUT)
#define STAGE_LITERAL "runtime-input"
#define SELF_ROOT_DEFAULT                                                    \
  "/root/vista-r8-ue57-stage-installers-r1/runtime-input"
#define INSTALLER_REVIEW_CANDIDATE_DEFAULT                                  \
  "/data/sysx/vista-world/runs/vista-action-world-r1/"                    \
  "vista-r8-ue57-runtime-input-stage-installer-review-candidate-"          \
  "20260830a/install-reconcile-r8-ue57-stage"
#define CANDIDATE_ROOT_DEFAULT                                               \
  "/data/sysx/vista-world/runs/vista-action-world-r1/"                    \
  "vista-r8-ue57-runtime-input-review-candidate-20260830a"
#define FINAL_ROOT_DEFAULT "/root/vista-r8-ue57-runtime-input-r1"
#define INSTALL_OPERATION "install-runtime-input-authority"
#define RECONCILE_OPERATION "reconcile-runtime-input-authority"
#define INSTALL_ACKNOWLEDGEMENT                                              \
  "I acknowledge one fresh publication of the externally reviewed VISTA " \
  "R8 UE 5.7 runtime input authority."
#define RECONCILE_ACKNOWLEDGEMENT                                            \
  "I acknowledge reconciliation of the externally reviewed VISTA R8 UE "  \
  "5.7 runtime input authority without republishing or deleting it."
#define PRIMARY_FILENAME "input-pin.json"
#define STAGE_HAS_SECONDARY 0
#elif defined(VISTA_R8_STAGE_RUNTIME_PLAN)
#define STAGE_LITERAL "runtime-plan"
#define SELF_ROOT_DEFAULT                                                    \
  "/root/vista-r8-ue57-stage-installers-r1/runtime-plan"
#define INSTALLER_REVIEW_CANDIDATE_DEFAULT                                  \
  "/data/sysx/vista-world/runs/vista-action-world-r1/"                    \
  "vista-r8-ue57-runtime-plan-stage-installer-review-candidate-"           \
  "20260830a/install-reconcile-r8-ue57-stage"
#define CANDIDATE_ROOT_DEFAULT                                               \
  "/data/sysx/vista-world/runs/vista-action-world-r1/"                    \
  "vista-r8-ue57-runtime-plan-review-candidate-20260830a"
#define FINAL_ROOT_DEFAULT "/root/vista-r8-ue57-runtime-plan-r1"
#define INSTALL_OPERATION "install-runtime-plan-authority"
#define RECONCILE_OPERATION "reconcile-runtime-plan-authority"
#define INSTALL_ACKNOWLEDGEMENT                                              \
  "I acknowledge one fresh publication of the externally reviewed VISTA " \
  "R8 UE 5.7 runtime plan authority."
#define RECONCILE_ACKNOWLEDGEMENT                                            \
  "I acknowledge reconciliation of the externally reviewed VISTA R8 UE "  \
  "5.7 runtime plan authority without republishing or deleting it."
#define PRIMARY_FILENAME "reviewed-plan-pin.json"
#define SECONDARY_FILENAME "publish-reconcile-r8-ue57"
#define STAGE_HAS_SECONDARY 1
#elif defined(VISTA_R8_STAGE_BUNDLE_INPUT)
#define STAGE_LITERAL "bundle-input"
#define SELF_ROOT_DEFAULT                                                    \
  "/root/vista-r8-ue57-stage-installers-r1/bundle-input"
#define INSTALLER_REVIEW_CANDIDATE_DEFAULT                                  \
  "/data/sysx/vista-world/runs/vista-action-world-r1/"                    \
  "vista-r8-ue57-bundle-input-stage-installer-review-candidate-"           \
  "20260830a/install-reconcile-r8-ue57-stage"
#define CANDIDATE_ROOT_DEFAULT                                               \
  "/data/sysx/vista-world/runs/vista-action-world-r1/"                    \
  "vista-r8-ue57-launcher-review-candidate-20260830a"
#define FINAL_ROOT_DEFAULT "/root/vista-r8-ue57-bundle-input-r1"
#define INSTALL_OPERATION "install-bundle-input-authority"
#define RECONCILE_OPERATION "reconcile-bundle-input-authority"
#define INSTALL_ACKNOWLEDGEMENT                                              \
  "I acknowledge one fresh publication of the externally reviewed VISTA " \
  "R8 UE 5.7 bundle input authority."
#define RECONCILE_ACKNOWLEDGEMENT                                            \
  "I acknowledge reconciliation of the externally reviewed VISTA R8 UE "  \
  "5.7 bundle input authority without republishing or deleting it."
#define PRIMARY_FILENAME "input-pin.json"
#define SECONDARY_FILENAME "launch-r8-ue57"
#define STAGE_HAS_SECONDARY 1
#else
#define STAGE_LITERAL "bundle-plan"
#define SELF_ROOT_DEFAULT                                                    \
  "/root/vista-r8-ue57-stage-installers-r1/bundle-plan"
#define INSTALLER_REVIEW_CANDIDATE_DEFAULT                                  \
  "/data/sysx/vista-world/runs/vista-action-world-r1/"                    \
  "vista-r8-ue57-bundle-plan-stage-installer-review-candidate-"            \
  "20260830a/install-reconcile-r8-ue57-stage"
#define CANDIDATE_ROOT_DEFAULT                                               \
  "/data/sysx/vista-world/runs/vista-action-world-r1/"                    \
  "vista-r8-ue57-bundle-plan-review-candidate-20260830a"
#define FINAL_ROOT_DEFAULT "/root/vista-r8-ue57-bundle-plan-r1"
#define INSTALL_OPERATION "install-bundle-plan-authority"
#define RECONCILE_OPERATION "reconcile-bundle-plan-authority"
#define INSTALL_ACKNOWLEDGEMENT                                              \
  "I acknowledge one fresh publication of the externally reviewed VISTA " \
  "R8 UE 5.7 bundle plan authority."
#define RECONCILE_ACKNOWLEDGEMENT                                            \
  "I acknowledge reconciliation of the externally reviewed VISTA R8 UE "  \
  "5.7 bundle plan authority without republishing or deleting it."
#define PRIMARY_FILENAME "reviewed-plan-pin.json"
#define SECONDARY_FILENAME "publish-reconcile-r8-ue57"
#define STAGE_HAS_SECONDARY 1
#endif

/* Keep the review-candidate literal in every production binary/receipt review. */
static const char installer_review_candidate_path[] __attribute__((used)) =
    INSTALLER_REVIEW_CANDIDATE_DEFAULT;

#ifdef VISTA_R8_STAGE_INSTALLER_TESTING
#ifndef VISTA_R8_TEST_SELF_ROOT
#error "VISTA_R8_TEST_SELF_ROOT is required in testing mode"
#endif
#ifndef VISTA_R8_TEST_CANDIDATE_ROOT
#error "VISTA_R8_TEST_CANDIDATE_ROOT is required in testing mode"
#endif
#ifndef VISTA_R8_TEST_FINAL_ROOT
#error "VISTA_R8_TEST_FINAL_ROOT is required in testing mode"
#endif
#ifndef VISTA_R8_TEST_HELPER_PATH
#error "VISTA_R8_TEST_HELPER_PATH is required in testing mode"
#endif
#ifndef VISTA_R8_TEST_REQUIRED_EUID
#error "VISTA_R8_TEST_REQUIRED_EUID is required in testing mode"
#endif
#ifndef VISTA_R8_TEST_REQUIRED_EGID
#error "VISTA_R8_TEST_REQUIRED_EGID is required in testing mode"
#endif
#ifndef VISTA_R8_TEST_SELF_UID
#error "VISTA_R8_TEST_SELF_UID is required in testing mode"
#endif
#ifndef VISTA_R8_TEST_SELF_GID
#error "VISTA_R8_TEST_SELF_GID is required in testing mode"
#endif
#ifndef VISTA_R8_TEST_REVIEW_UID
#error "VISTA_R8_TEST_REVIEW_UID is required in testing mode"
#endif
#ifndef VISTA_R8_TEST_REVIEW_GID
#error "VISTA_R8_TEST_REVIEW_GID is required in testing mode"
#endif
#ifndef VISTA_R8_TEST_HELPER_UID
#error "VISTA_R8_TEST_HELPER_UID is required in testing mode"
#endif
#ifndef VISTA_R8_TEST_HELPER_GID
#error "VISTA_R8_TEST_HELPER_GID is required in testing mode"
#endif
#define SELF_ROOT VISTA_R8_TEST_SELF_ROOT
#define CANDIDATE_ROOT VISTA_R8_TEST_CANDIDATE_ROOT
#define FINAL_ROOT VISTA_R8_TEST_FINAL_ROOT
#define CORE_HELPER_PATH VISTA_R8_TEST_HELPER_PATH
#define REQUIRED_EUID ((uid_t)VISTA_R8_TEST_REQUIRED_EUID)
#define REQUIRED_EGID ((gid_t)VISTA_R8_TEST_REQUIRED_EGID)
#define SELF_UID ((uid_t)VISTA_R8_TEST_SELF_UID)
#define SELF_GID ((gid_t)VISTA_R8_TEST_SELF_GID)
#define REVIEW_UID ((uid_t)VISTA_R8_TEST_REVIEW_UID)
#define REVIEW_GID ((gid_t)VISTA_R8_TEST_REVIEW_GID)
#define HELPER_UID ((uid_t)VISTA_R8_TEST_HELPER_UID)
#define HELPER_GID ((gid_t)VISTA_R8_TEST_HELPER_GID)
#else
#define SELF_ROOT SELF_ROOT_DEFAULT
#define CANDIDATE_ROOT CANDIDATE_ROOT_DEFAULT
#define FINAL_ROOT FINAL_ROOT_DEFAULT
#define CORE_HELPER_PATH CORE_HELPER_PATH_DEFAULT
#define REQUIRED_EUID ((uid_t)0)
#define REQUIRED_EGID ((gid_t)0)
#define SELF_UID ((uid_t)0)
#define SELF_GID ((gid_t)0)
#define REVIEW_UID ((uid_t)1000021)
#define REVIEW_GID ((gid_t)1000001)
#define HELPER_UID ((uid_t)0)
#define HELPER_GID ((gid_t)0)
#endif

#define EXPECTED_SELF_PATH SELF_ROOT "/" INSTALLER_FILENAME
#define PYTHON_PATH PYTHON_PATH_DEFAULT

enum {
  FAILURE_EXIT = 126,
  SEALED_DIRECTORY_MODE = 0555,
  INSTALLER_MODE = 0555,
  RECEIPT_MODE = 0444,
  PIN_DOCUMENT_MODE = 0444,
  EXECUTABLE_MODE = 0555,
  PYTHON_MODE = 0755,
  HELPER_MODE = 0500,
  MAX_RECEIPT_BYTES = 1024 * 1024,
  MAX_INPUT_DOCUMENT_BYTES = 128 * 1024 * 1024,
  MAX_PINNED_FILE_BYTES = 128 * 1024 * 1024,
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
  uid_t uid;
  gid_t gid;
  int descriptor;
  struct stat metadata;
  file_pin pin;
  int pin_is_set;
} held_file;

typedef struct {
  const char *path;
  int descriptor;
  struct stat metadata;
  held_file files[2];
  size_t file_count;
} held_tree;

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
    uint32_t sigma_zero =
        rotate_right(a, 2) ^ rotate_right(a, 13) ^ rotate_right(a, 22);
    uint32_t sigma_one =
        rotate_right(e, 6) ^ rotate_right(e, 11) ^ rotate_right(e, 25);
    uint32_t first = h + sigma_one + choice +
                     sha256_round_constants[index] + words[index];
    uint32_t second = sigma_zero + majority;

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

static void digest_to_hex(const unsigned char digest[32], char output[65]) {
  static const char hexadecimal[] = "0123456789abcdef";
  int index;
  for (index = 0; index < 32; ++index) {
    output[2 * index] = hexadecimal[digest[index] >> 4];
    output[2 * index + 1] = hexadecimal[digest[index] & 15];
  }
  output[64] = '\0';
}

static int valid_sha256_literal(const char *value) {
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

static int hash_fd_bounded(int descriptor, off_t exact_size,
                           file_pin *result) {
  unsigned char buffer[64 * 1024];
  unsigned char digest[32];
  sha256_context context;
  off_t total = 0;
  ssize_t observed;

  if (exact_size <= 0 || exact_size > MAX_PINNED_FILE_BYTES ||
      lseek(descriptor, 0, SEEK_SET) < 0) {
    return -1;
  }
  sha256_initialize(&context);
  while (total < exact_size) {
    size_t remaining = (size_t)(exact_size - total);
    size_t requested = remaining < sizeof(buffer) ? remaining : sizeof(buffer);
    observed = read(descriptor, buffer, requested);
    if (observed <= 0 || observed > exact_size - total) {
      return -1;
    }
    total += observed;
    sha256_update(&context, buffer, (size_t)observed);
  }
  observed = read(descriptor, buffer, 1);
  if (observed != 0 || total != exact_size ||
      lseek(descriptor, 0, SEEK_SET) < 0) {
    return -1;
  }
  sha256_finalize(&context, digest);
  digest_to_hex(digest, result->sha256);
  result->size_bytes = total;
  return 0;
}

static int verify_fd_pin(int descriptor, const file_pin *expected) {
  file_pin actual;
  struct stat metadata;
  if (expected->size_bytes <= 0 ||
      expected->size_bytes > MAX_PINNED_FILE_BYTES ||
      !valid_sha256_literal(expected->sha256) ||
      fstat(descriptor, &metadata) != 0 ||
      !S_ISREG(metadata.st_mode) ||
      metadata.st_size != expected->size_bytes ||
      hash_fd_bounded(descriptor, expected->size_bytes, &actual) != 0) {
    return -1;
  }
  return actual.size_bytes == expected->size_bytes &&
                 strcmp(actual.sha256, expected->sha256) == 0
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
         left->st_mode == right->st_mode &&
         left->st_uid == right->st_uid && left->st_gid == right->st_gid &&
         left->st_nlink == right->st_nlink &&
         left->st_size == right->st_size &&
         left->st_mtim.tv_sec == right->st_mtim.tv_sec &&
         left->st_mtim.tv_nsec == right->st_mtim.tv_nsec &&
         left->st_ctim.tv_sec == right->st_ctim.tv_sec &&
         left->st_ctim.tv_nsec == right->st_ctim.tv_nsec;
}

static int verify_directory_fd(int descriptor, mode_t mode, uid_t uid,
                               gid_t gid, struct stat *result) {
  struct stat metadata;
  if (fstat(descriptor, &metadata) != 0 ||
      !S_ISDIR(metadata.st_mode) || metadata.st_nlink != 2 ||
      metadata.st_uid != uid || metadata.st_gid != gid ||
      (metadata.st_mode & 07777) != mode) {
    return -1;
  }
  if (result != NULL) {
    *result = metadata;
  }
  return 0;
}

static int verify_regular_fd(int descriptor, mode_t mode, uid_t uid,
                             gid_t gid, struct stat *result) {
  struct stat metadata;
  if (fstat(descriptor, &metadata) != 0 ||
      !S_ISREG(metadata.st_mode) || metadata.st_nlink != 1 ||
      metadata.st_uid != uid || metadata.st_gid != gid ||
      (metadata.st_mode & 07777) != mode) {
    return -1;
  }
  if (result != NULL) {
    *result = metadata;
  }
  return 0;
}

/* Open every absolute-path component with O_NOFOLLOW. */
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

static int open_directory_nofollow(const char *path, mode_t mode, uid_t uid,
                                   gid_t gid, struct stat *metadata) {
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
      verify_directory_fd(descriptor, mode, uid, gid, metadata) != 0) {
    if (descriptor >= 0) {
      (void)close(descriptor);
    }
    return -1;
  }
  return descriptor;
}

static int open_regular_nofollow(const char *path, mode_t mode, uid_t uid,
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
      verify_regular_fd(descriptor, mode, uid, gid, metadata) != 0) {
    if (descriptor >= 0) {
      (void)close(descriptor);
    }
    return -1;
  }
  return descriptor;
}

static int exact_inventory(int directory, held_file *files,
                           size_t file_count) {
  unsigned char seen[2] = {0, 0};
  int duplicate = openat(directory, ".",
                         O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
  DIR *stream;
  struct dirent *entry;
  size_t observed = 0;

  if (file_count > 2 || duplicate < 0) {
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
    for (index = 0; index < file_count; ++index) {
      if (strcmp(entry->d_name, files[index].name) == 0 && !seen[index]) {
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
  if (errno != 0 || closedir(stream) != 0 || observed != file_count) {
    return -1;
  }
  return 0;
}

static int open_tree(held_tree *tree) {
  size_t index;
  tree->descriptor = open_directory_nofollow(
      tree->path, SEALED_DIRECTORY_MODE, tree->files[0].uid,
      tree->files[0].gid, &tree->metadata);
  if (tree->descriptor < 0 ||
      exact_inventory(tree->descriptor, tree->files, tree->file_count) != 0) {
    return -1;
  }
  for (index = 0; index < tree->file_count; ++index) {
    held_file *file = &tree->files[index];
    file->descriptor =
        openat(tree->descriptor, file->name,
               O_RDONLY | O_NONBLOCK | O_NOFOLLOW | O_CLOEXEC);
    if (file->descriptor < 0 ||
        verify_regular_fd(file->descriptor, file->mode, file->uid, file->gid,
                          &file->metadata) != 0 ||
        (file->pin_is_set && verify_fd_pin(file->descriptor, &file->pin) != 0)) {
      return -1;
    }
  }
  return 0;
}

static int revalidate_tree(held_tree *tree) {
  struct stat directory_metadata;
  struct stat reopened_metadata;
  int reopened;
  size_t index;

  if (verify_directory_fd(tree->descriptor, SEALED_DIRECTORY_MODE,
                          tree->files[0].uid, tree->files[0].gid,
                          &directory_metadata) != 0 ||
      !same_identity(&tree->metadata, &directory_metadata) ||
      exact_inventory(tree->descriptor, tree->files, tree->file_count) != 0) {
    return -1;
  }
  reopened = open_directory_nofollow(
      tree->path, SEALED_DIRECTORY_MODE, tree->files[0].uid,
      tree->files[0].gid, &reopened_metadata);
  if (reopened < 0 || !same_identity(&tree->metadata, &reopened_metadata) ||
      exact_inventory(reopened, tree->files, tree->file_count) != 0) {
    if (reopened >= 0) {
      (void)close(reopened);
    }
    return -1;
  }
  for (index = 0; index < tree->file_count; ++index) {
    held_file *file = &tree->files[index];
    struct stat held_metadata;
    struct stat reopened_file_metadata;
    int reopened_file;
    if (!file->pin_is_set ||
        verify_regular_fd(file->descriptor, file->mode, file->uid, file->gid,
                          &held_metadata) != 0 ||
        !same_identity(&file->metadata, &held_metadata) ||
        verify_fd_pin(file->descriptor, &file->pin) != 0) {
      (void)close(reopened);
      return -1;
    }
    reopened_file = openat(reopened, file->name,
                           O_RDONLY | O_NONBLOCK | O_NOFOLLOW | O_CLOEXEC);
    if (reopened_file < 0 ||
        verify_regular_fd(reopened_file, file->mode, file->uid, file->gid,
                          &reopened_file_metadata) != 0 ||
        !same_identity(&file->metadata, &reopened_file_metadata) ||
        verify_fd_pin(reopened_file, &file->pin) != 0) {
      if (reopened_file >= 0) {
        (void)close(reopened_file);
      }
      (void)close(reopened);
      return -1;
    }
    (void)close(reopened_file);
  }
  (void)close(reopened);
  return 0;
}

static int fixed_path_is_absent(const char *path) {
  char name[NAME_MAX + 1];
  struct stat metadata;
  int parent;
  int result;
  if (open_parent_nofollow(path, &parent, name) != 0) {
    return -1;
  }
  errno = 0;
  result = fstatat(parent, name, &metadata, AT_SYMLINK_NOFOLLOW);
  (void)close(parent);
  return result < 0 && errno == ENOENT ? 0 : -1;
}

static unsigned char *read_exact_file(int descriptor, off_t expected_size,
                                      size_t limit) {
  unsigned char *result;
  size_t total = 0;
  if (expected_size <= 0 || (uintmax_t)expected_size > (uintmax_t)limit ||
      (uintmax_t)expected_size >= (uintmax_t)SIZE_MAX) {
    return NULL;
  }
  result = malloc((size_t)expected_size + 1);
  if (result == NULL || lseek(descriptor, 0, SEEK_SET) < 0) {
    free(result);
    return NULL;
  }
  while (total < (size_t)expected_size) {
    ssize_t observed =
        read(descriptor, result + total, (size_t)expected_size - total);
    if (observed <= 0) {
      free(result);
      return NULL;
    }
    total += (size_t)observed;
  }
  if (read(descriptor, result + total, 1) != 0 ||
      lseek(descriptor, 0, SEEK_SET) < 0) {
    free(result);
    return NULL;
  }
  result[total] = '\0';
  return result;
}

static int parse_decimal_size(const char *start, const char *limit,
                              const char **end_result, off_t *result) {
  uintmax_t value = 0;
  const char *cursor = start;
  if (cursor >= limit || *cursor < '1' || *cursor > '9') {
    return -1;
  }
  while (cursor < limit && *cursor >= '0' && *cursor <= '9') {
    unsigned int digit = (unsigned int)(*cursor - '0');
    if (value > ((uintmax_t)INT64_MAX - digit) / 10u) {
      return -1;
    }
    value = value * 10u + digit;
    ++cursor;
  }
  *result = (off_t)value;
  *end_result = cursor;
  return 0;
}

static int extract_pin(const unsigned char *document, size_t document_size,
                       const char *prefix, const char *suffix,
                       file_pin *result) {
  const char *text = (const char *)document;
  size_t prefix_size = strlen(prefix);
  size_t suffix_size = strlen(suffix);
  const char *limit = text + document_size;
  const char *match = memmem(text, document_size, prefix, prefix_size);
  const char *cursor;
  size_t index;
  if (match == NULL ||
      memmem(match + 1, (size_t)(limit - (match + 1)), prefix,
             prefix_size) != NULL) {
    return -1;
  }
  cursor = match + prefix_size;
  if ((size_t)(limit - cursor) < 64u + 15u + 1u + suffix_size) {
    return -1;
  }
  for (index = 0; index < 64; ++index) {
    char value = cursor[index];
    if (!((value >= '0' && value <= '9') ||
          (value >= 'a' && value <= 'f'))) {
      return -1;
    }
    result->sha256[index] = value;
  }
  result->sha256[64] = '\0';
  cursor += 64;
  if ((size_t)(limit - cursor) < 15 ||
      memcmp(cursor, "\",\"size_bytes\":", 15) != 0) {
    return -1;
  }
  cursor += 15;
  if (parse_decimal_size(cursor, limit, &cursor, &result->size_bytes) != 0 ||
      (size_t)(limit - cursor) < suffix_size ||
      memcmp(cursor, suffix, suffix_size) != 0) {
    return -1;
  }
  return 0;
}

static int extract_installer_pin(const unsigned char *receipt,
                                 size_t receipt_size, file_pin *result) {
  char prefix[PATH_MAX + 80];
  int length = snprintf(prefix, sizeof(prefix),
                        "\"installer\":{\"path\":\"%s\",\"pin\":{\"sha256\":\"",
                        EXPECTED_SELF_PATH);
  if (length < 0 || (size_t)length >= sizeof(prefix)) {
    return -1;
  }
  return extract_pin(receipt, receipt_size, prefix, "}}", result);
}

#if defined(VISTA_R8_STAGE_BUNDLE_INPUT)
static int extract_bundle_launcher_pin(const unsigned char *input_document,
                                       size_t input_size, file_pin *result) {
  return extract_pin(input_document, input_size,
                     "\"launcher_binary_pin\":{\"sha256\":\"", "}", result);
}
#endif

static int clear_close_on_exec(int descriptor) {
  int flags = fcntl(descriptor, F_GETFD);
  return flags < 0 ||
                 fcntl(descriptor, F_SETFD, flags & ~FD_CLOEXEC) != 0
             ? -1
             : 0;
}

static int revalidate_pinned_path(const char *path, int held_descriptor,
                                  const struct stat *held_metadata,
                                  mode_t mode, uid_t uid, gid_t gid,
                                  const file_pin *pin) {
  struct stat current_metadata;
  struct stat reopened_metadata;
  int reopened;
  if (verify_regular_fd(held_descriptor, mode, uid, gid, &current_metadata) !=
          0 ||
      !same_identity(held_metadata, &current_metadata) ||
      verify_fd_pin(held_descriptor, pin) != 0) {
    return -1;
  }
  reopened = open_regular_nofollow(path, mode, uid, gid, &reopened_metadata);
  if (reopened < 0 || !same_identity(held_metadata, &reopened_metadata) ||
      verify_fd_pin(reopened, pin) != 0) {
    if (reopened >= 0) {
      (void)close(reopened);
    }
    return -1;
  }
  (void)close(reopened);
  return 0;
}

static void initialize_candidate_tree(held_tree *tree) {
  memset(tree, 0, sizeof(*tree));
  tree->path = CANDIDATE_ROOT;
  tree->descriptor = -1;
  tree->file_count = STAGE_HAS_SECONDARY ? 2u : 1u;
  tree->files[0].name = PRIMARY_FILENAME;
  tree->files[0].mode = PIN_DOCUMENT_MODE;
  tree->files[0].uid = REVIEW_UID;
  tree->files[0].gid = REVIEW_GID;
  tree->files[0].descriptor = -1;
#if defined(VISTA_R8_STAGE_RUNTIME_INPUT) ||                              \
    defined(VISTA_R8_STAGE_BUNDLE_INPUT)
  memcpy(tree->files[0].pin.sha256, EXPECTED_INPUT_PIN_SHA256, 65);
  tree->files[0].pin.size_bytes = (off_t)EXPECTED_INPUT_PIN_SIZE;
#else
  memcpy(tree->files[0].pin.sha256, EXPECTED_REVIEWED_PLAN_PIN_SHA256, 65);
  tree->files[0].pin.size_bytes = (off_t)EXPECTED_REVIEWED_PLAN_PIN_SIZE;
#endif
  tree->files[0].pin_is_set = 1;
#if STAGE_HAS_SECONDARY
  tree->files[1].name = SECONDARY_FILENAME;
  tree->files[1].mode = EXECUTABLE_MODE;
  tree->files[1].uid = REVIEW_UID;
  tree->files[1].gid = REVIEW_GID;
  tree->files[1].descriptor = -1;
#if defined(VISTA_R8_STAGE_RUNTIME_PLAN) ||                               \
    defined(VISTA_R8_STAGE_BUNDLE_PLAN)
  memcpy(tree->files[1].pin.sha256, EXPECTED_ADMIN_LAUNCHER_SHA256, 65);
  tree->files[1].pin.size_bytes = (off_t)EXPECTED_ADMIN_LAUNCHER_SIZE;
  tree->files[1].pin_is_set = 1;
#endif
#endif
}

static void initialize_final_tree(held_tree *tree,
                                  const held_tree *candidate) {
  size_t index;
  memset(tree, 0, sizeof(*tree));
  tree->path = FINAL_ROOT;
  tree->descriptor = -1;
  tree->file_count = candidate->file_count;
  for (index = 0; index < tree->file_count; ++index) {
    tree->files[index] = candidate->files[index];
    tree->files[index].uid = SELF_UID;
    tree->files[index].gid = SELF_GID;
    tree->files[index].descriptor = -1;
    memset(&tree->files[index].metadata, 0,
           sizeof(tree->files[index].metadata));
  }
}

int main(int argc, char **argv) {
  const char *operation;
  const char *acknowledgement;
  held_tree self_tree;
  held_tree candidate_tree;
  held_tree final_tree;
  struct stat live_self_metadata;
  struct stat python_metadata;
  struct stat helper_metadata;
  file_pin python_pin = {EXPECTED_PYTHON_SHA256, (off_t)EXPECTED_PYTHON_SIZE};
  file_pin helper_pin = {EXPECTED_HELPER_SHA256, (off_t)EXPECTED_HELPER_SIZE};
  unsigned char *receipt = NULL;
#if defined(VISTA_R8_STAGE_BUNDLE_INPUT)
  unsigned char *input_document = NULL;
#endif
  int live_self_descriptor = -1;
  int python_descriptor = -1;
  int helper_descriptor = -1;
  char helper_fd_path[64];
  char installer_fd_text[32];
  int helper_fd_length;
  int installer_fd_length;
  int is_reconcile;

  if (argc != 3) {
    return fail("R8_STAGE_INSTALLER: exactly operation and acknowledgement required");
  }
  if (strcmp(argv[1], INSTALL_OPERATION) == 0) {
    operation = INSTALL_OPERATION;
    acknowledgement = INSTALL_ACKNOWLEDGEMENT;
    is_reconcile = 0;
  } else if (strcmp(argv[1], RECONCILE_OPERATION) == 0) {
    operation = RECONCILE_OPERATION;
    acknowledgement = RECONCILE_ACKNOWLEDGEMENT;
    is_reconcile = 1;
  } else {
    return fail("R8_STAGE_INSTALLER: operation differs from compiled stage");
  }
  if (strcmp(argv[2], acknowledgement) != 0) {
    return fail("R8_STAGE_INSTALLER: acknowledgement differs");
  }
  if (geteuid() != REQUIRED_EUID || getegid() != REQUIRED_EGID) {
    return fail("R8_STAGE_INSTALLER: root EUID and EGID required");
  }
  if (!valid_sha256_literal(EXPECTED_PYTHON_SHA256) ||
      !valid_sha256_literal(EXPECTED_HELPER_SHA256)) {
    return fail("R8_STAGE_INSTALLER: compiled tool pin is invalid");
  }

  memset(&self_tree, 0, sizeof(self_tree));
  self_tree.path = SELF_ROOT;
  self_tree.descriptor = -1;
  self_tree.file_count = 2;
  self_tree.files[0] = (held_file){
      INSTALLER_FILENAME, INSTALLER_MODE, SELF_UID, SELF_GID, -1,
      {0}, {{0}, 0}, 0};
  self_tree.files[1] = (held_file){
      RECEIPT_FILENAME, RECEIPT_MODE, SELF_UID, SELF_GID, -1,
      {0}, {{0}, 0}, 0};
  if (open_tree(&self_tree) != 0) {
    return fail("R8_STAGE_INSTALLER: installed self authority differs");
  }
  if (self_tree.files[1].metadata.st_size <= 0 ||
      self_tree.files[1].metadata.st_size > MAX_RECEIPT_BYTES ||
      hash_fd_bounded(self_tree.files[1].descriptor,
                      self_tree.files[1].metadata.st_size,
                      &self_tree.files[1].pin) != 0) {
    return fail("R8_STAGE_INSTALLER: receipt hash failed");
  }
  self_tree.files[1].pin_is_set = 1;
  receipt = read_exact_file(self_tree.files[1].descriptor,
                            self_tree.files[1].pin.size_bytes,
                            MAX_RECEIPT_BYTES);
  if (receipt == NULL ||
      extract_installer_pin(receipt,
                            (size_t)self_tree.files[1].pin.size_bytes,
                            &self_tree.files[0].pin) != 0 ||
      verify_fd_pin(self_tree.files[0].descriptor,
                    &self_tree.files[0].pin) != 0) {
    return fail("R8_STAGE_INSTALLER: receipt does not bind installed self");
  }
  self_tree.files[0].pin_is_set = 1;

  live_self_descriptor =
      open("/proc/self/exe", O_RDONLY | O_NONBLOCK | O_CLOEXEC);
  if (live_self_descriptor < 0 ||
      verify_regular_fd(live_self_descriptor, INSTALLER_MODE, SELF_UID,
                        SELF_GID, &live_self_metadata) != 0 ||
      !same_identity(&self_tree.files[0].metadata, &live_self_metadata) ||
      verify_fd_pin(live_self_descriptor, &self_tree.files[0].pin) != 0) {
    return fail("R8_STAGE_INSTALLER: live self identity differs");
  }

  initialize_candidate_tree(&candidate_tree);
  initialize_final_tree(&final_tree, &candidate_tree);
  if (is_reconcile) {
    if (open_tree(&final_tree) != 0) {
      return fail("R8_STAGE_INSTALLER: reconcile final authority differs");
    }
  } else if (open_tree(&candidate_tree) != 0) {
    return fail("R8_STAGE_INSTALLER: reviewed candidate differs");
  }
#if defined(VISTA_R8_STAGE_BUNDLE_INPUT)
  {
    held_tree *selected_tree = is_reconcile ? &final_tree : &candidate_tree;
    input_document = read_exact_file(selected_tree->files[0].descriptor,
                                   selected_tree->files[0].pin.size_bytes,
                                   MAX_INPUT_DOCUMENT_BYTES);
    if (input_document == NULL ||
        extract_bundle_launcher_pin(input_document,
                                    (size_t)selected_tree->files[0].pin.size_bytes,
                                    &selected_tree->files[1].pin) != 0 ||
        verify_fd_pin(selected_tree->files[1].descriptor,
                      &selected_tree->files[1].pin) != 0) {
      return fail("R8_STAGE_INSTALLER: bundle launcher transitive pin differs");
    }
    selected_tree->files[1].pin_is_set = 1;
  }
#endif
  if (!is_reconcile && fixed_path_is_absent(FINAL_ROOT) != 0) {
    return fail("R8_STAGE_INSTALLER: install final path is not fresh");
  }

  python_descriptor = open_regular_nofollow(
      PYTHON_PATH, PYTHON_MODE, (uid_t)0, (gid_t)0, &python_metadata);
  helper_descriptor = open_regular_nofollow(
      CORE_HELPER_PATH, HELPER_MODE, HELPER_UID, HELPER_GID, &helper_metadata);
  if (python_descriptor < 0 || helper_descriptor < 0 ||
      verify_fd_pin(python_descriptor, &python_pin) != 0 ||
      verify_fd_pin(helper_descriptor, &helper_pin) != 0) {
    return fail("R8_STAGE_INSTALLER: held helper or Python differs");
  }

  if (revalidate_tree(&self_tree) != 0 ||
      (!is_reconcile && revalidate_tree(&candidate_tree) != 0) ||
      (is_reconcile && revalidate_tree(&final_tree) != 0) ||
      (!is_reconcile && fixed_path_is_absent(FINAL_ROOT) != 0) ||
      revalidate_pinned_path(PYTHON_PATH, python_descriptor, &python_metadata,
                             PYTHON_MODE, (uid_t)0, (gid_t)0,
                             &python_pin) != 0 ||
      revalidate_pinned_path(CORE_HELPER_PATH, helper_descriptor,
                             &helper_metadata, HELPER_MODE, HELPER_UID,
                             HELPER_GID, &helper_pin) != 0 ||
      verify_regular_fd(live_self_descriptor, INSTALLER_MODE, SELF_UID,
                        SELF_GID, NULL) != 0 ||
      verify_fd_pin(live_self_descriptor, &self_tree.files[0].pin) != 0 ||
      clear_close_on_exec(helper_descriptor) != 0 ||
      clear_close_on_exec(self_tree.files[0].descriptor) != 0) {
    return fail("R8_STAGE_INSTALLER: held authority identity drifted");
  }

  helper_fd_length = snprintf(helper_fd_path, sizeof(helper_fd_path),
                              "/proc/self/fd/%d", helper_descriptor);
  installer_fd_length = snprintf(installer_fd_text, sizeof(installer_fd_text),
                                 "%d", self_tree.files[0].descriptor);
  if (helper_fd_length < 0 ||
      (size_t)helper_fd_length >= sizeof(helper_fd_path) ||
      installer_fd_length < 0 ||
      (size_t)installer_fd_length >= sizeof(installer_fd_text)) {
    return fail("R8_STAGE_INSTALLER: inherited descriptor formatting failed");
  }

  {
#if defined(VISTA_R8_STAGE_RUNTIME_INPUT) ||                              \
    defined(VISTA_R8_STAGE_BUNDLE_INPUT)
    char *const child_argv[] = {
        PYTHON_PATH,
        "-I",
        "-B",
        helper_fd_path,
        (char *)operation,
        "--reviewed-input-sha256",
        EXPECTED_INPUT_PIN_SHA256,
        "--reviewed-input-size",
        STRINGIFY(EXPECTED_INPUT_PIN_SIZE),
        "--stage-installer-fd",
        installer_fd_text,
        "--acknowledgement",
        (char *)acknowledgement,
        NULL,
    };
#else
    char *const child_argv[] = {
        PYTHON_PATH,
        "-I",
        "-B",
        helper_fd_path,
        (char *)operation,
        "--reviewed-plan-sha256",
        EXPECTED_REVIEWED_PLAN_PIN_SHA256,
        "--reviewed-plan-size",
        STRINGIFY(EXPECTED_REVIEWED_PLAN_PIN_SIZE),
        "--reviewed-admin-sha256",
        EXPECTED_ADMIN_LAUNCHER_SHA256,
        "--reviewed-admin-size",
        STRINGIFY(EXPECTED_ADMIN_LAUNCHER_SIZE),
        "--stage-installer-fd",
        installer_fd_text,
        "--acknowledgement",
        (char *)acknowledgement,
        NULL,
    };
#endif
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
  return fail("R8_STAGE_INSTALLER: held-Python execveat failed");
}
