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
 * Finite manual trust boundary for the R8 UE 5.7 initial bootstrap.
 *
 * A reviewer independently conveys the hash and size of this static ELF.  An
 * administrator copies that one binary into the fixed, root-owned, one-file
 * SELF_ROOT.  No caller supplies paths, pins, modes, or a staging directory.
 * The binary embeds the exact three-file dedicated-builder Phase-B candidate
 * and installs it append-only as the four-file initial-bootstrap authority.
 * Reconciliation is candidate-free and fsync-only.
 */

#ifndef EXPECTED_LAUNCHER_SHA256
#error "EXPECTED_LAUNCHER_SHA256 is required"
#endif
#ifndef EXPECTED_LAUNCHER_SIZE
#error "EXPECTED_LAUNCHER_SIZE is required"
#endif
#ifndef EXPECTED_HELPER_SHA256
#error "EXPECTED_HELPER_SHA256 is required"
#endif
#ifndef EXPECTED_HELPER_SIZE
#error "EXPECTED_HELPER_SIZE is required"
#endif
#ifndef EXPECTED_INPUT_PIN_SHA256
#error "EXPECTED_INPUT_PIN_SHA256 is required"
#endif
#ifndef EXPECTED_INPUT_PIN_SIZE
#error "EXPECTED_INPUT_PIN_SIZE is required"
#endif

_Static_assert(sizeof(EXPECTED_LAUNCHER_SHA256) == 65,
               "launcher SHA-256 must contain 64 bytes");
_Static_assert(sizeof(EXPECTED_HELPER_SHA256) == 65,
               "helper SHA-256 must contain 64 bytes");
_Static_assert(sizeof(EXPECTED_INPUT_PIN_SHA256) == 65,
               "input SHA-256 must contain 64 bytes");
_Static_assert(EXPECTED_LAUNCHER_SIZE > 0, "launcher size must be positive");
_Static_assert(EXPECTED_HELPER_SIZE > 0, "helper size must be positive");
_Static_assert(EXPECTED_INPUT_PIN_SIZE > 0, "input size must be positive");

#define INSTALLER_NAME "install-reconcile-r8-ue57-initial-bootstrap"
#define LAUNCHER_NAME "bootstrap-r8-ue57-initial-authorities"
#define HELPER_NAME "vista_r8_ue57_initial_bootstrap.py"
#define INPUT_NAME "input-pin.json"
#define LOCK_NAME ".bootstrap.lock"

#define SELF_ROOT_DEFAULT                                                     \
  "/root/vista-r8-ue57-initial-bootstrap-installer-r2"
#define CANDIDATE_ROOT_DEFAULT                                                \
  "/var/lib/vista-r8-native-builder-r2/phase-b-slot/published/"             \
  "initial-bootstrap-candidate"
#define FINAL_ROOT_DEFAULT "/root/vista-r8-ue57-initial-bootstrap-r2"
#define ROOT_PARENT_DEFAULT "/root"

#define INSTALL_OPERATION "install-initial-bootstrap"
#define RECONCILE_OPERATION "reconcile-initial-bootstrap"
#define INSTALL_ACK                                                               \
  "I acknowledge one fresh no-replace installation of the externally "          \
  "reviewed VISTA R8 UE 5.7 initial bootstrap authority."
#define RECONCILE_ACK                                                             \
  "I acknowledge candidate-free fsync reconciliation of the existing VISTA "    \
  "R8 UE 5.7 initial bootstrap authority without creating, deleting, "           \
  "renaming, chmodding, or repairing it."

#ifdef VISTA_R8_INITIAL_INSTALLER_TESTING
#ifndef VISTA_R8_TEST_SELF_ROOT
#error "VISTA_R8_TEST_SELF_ROOT is required"
#endif
#ifndef VISTA_R8_TEST_CANDIDATE_ROOT
#error "VISTA_R8_TEST_CANDIDATE_ROOT is required"
#endif
#ifndef VISTA_R8_TEST_FINAL_ROOT
#error "VISTA_R8_TEST_FINAL_ROOT is required"
#endif
#ifndef VISTA_R8_TEST_ROOT_PARENT
#error "VISTA_R8_TEST_ROOT_PARENT is required"
#endif
#ifndef VISTA_R8_TEST_REQUIRED_EUID
#error "VISTA_R8_TEST_REQUIRED_EUID is required"
#endif
#ifndef VISTA_R8_TEST_REQUIRED_EGID
#error "VISTA_R8_TEST_REQUIRED_EGID is required"
#endif
#ifndef VISTA_R8_TEST_REVIEW_UID
#error "VISTA_R8_TEST_REVIEW_UID is required"
#endif
#ifndef VISTA_R8_TEST_REVIEW_GID
#error "VISTA_R8_TEST_REVIEW_GID is required"
#endif
#define SELF_ROOT VISTA_R8_TEST_SELF_ROOT
#define CANDIDATE_ROOT VISTA_R8_TEST_CANDIDATE_ROOT
#define FINAL_ROOT VISTA_R8_TEST_FINAL_ROOT
#define ROOT_PARENT VISTA_R8_TEST_ROOT_PARENT
#define REQUIRED_EUID ((uid_t)VISTA_R8_TEST_REQUIRED_EUID)
#define REQUIRED_EGID ((gid_t)VISTA_R8_TEST_REQUIRED_EGID)
#define REVIEW_UID ((uid_t)VISTA_R8_TEST_REVIEW_UID)
#define REVIEW_GID ((gid_t)VISTA_R8_TEST_REVIEW_GID)
#define ROOT_UID ((uid_t)VISTA_R8_TEST_REQUIRED_EUID)
#define ROOT_GID ((gid_t)VISTA_R8_TEST_REQUIRED_EGID)
#else
#define SELF_ROOT SELF_ROOT_DEFAULT
#define CANDIDATE_ROOT CANDIDATE_ROOT_DEFAULT
#define FINAL_ROOT FINAL_ROOT_DEFAULT
#define ROOT_PARENT ROOT_PARENT_DEFAULT
#define REQUIRED_EUID ((uid_t)0)
#define REQUIRED_EGID ((gid_t)0)
#define REVIEW_UID ((uid_t)997)
#define REVIEW_GID ((gid_t)997)
#define ROOT_UID ((uid_t)0)
#define ROOT_GID ((gid_t)0)
#endif

#define EXPECTED_SELF_PATH SELF_ROOT "/" INSTALLER_NAME

enum {
  FAILURE_EXIT = 126,
  SEALED_DIRECTORY_MODE = 0555,
  PRIVATE_DIRECTORY_MODE = 0700,
  INSTALLER_MODE = 0500,
  CANDIDATE_LAUNCHER_MODE = 0555,
  CANDIDATE_DATA_MODE = 0444,
  FINAL_LAUNCHER_MODE = 0500,
  FINAL_HELPER_MODE = 0500,
  FINAL_INPUT_MODE = 0444,
  FINAL_LOCK_MODE = 0600,
  MAX_PINNED_BYTES = 64 * 1024 * 1024,
  COPY_CHUNK_BYTES = 64 * 1024,
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
} file_pin;

typedef struct {
  const char *name;
  mode_t mode;
  uid_t uid;
  gid_t gid;
  file_pin pin;
  int descriptor;
  struct stat metadata;
} held_file;

typedef struct {
  const char *path;
  uid_t uid;
  gid_t gid;
  mode_t mode;
  held_file *files;
  size_t file_count;
  int descriptor;
  struct stat metadata;
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
  a = context->state[0]; b = context->state[1];
  c = context->state[2]; d = context->state[3];
  e = context->state[4]; f = context->state[5];
  g = context->state[6]; h = context->state[7];
  for (index = 0; index < 64; ++index) {
    uint32_t choice = (e & f) ^ ((~e) & g);
    uint32_t majority = (a & b) ^ (a & c) ^ (b & c);
    uint32_t s0 = rotate_right(a, 2) ^ rotate_right(a, 13) ^
                  rotate_right(a, 22);
    uint32_t s1 = rotate_right(e, 6) ^ rotate_right(e, 11) ^
                  rotate_right(e, 25);
    uint32_t first = h + s1 + choice + sha256_round_constants[index] +
                     words[index];
    uint32_t second = s0 + majority;
    h = g; g = f; f = e; e = d + first;
    d = c; c = b; b = a; a = first + second;
  }
  context->state[0] += a; context->state[1] += b;
  context->state[2] += c; context->state[3] += d;
  context->state[4] += e; context->state[5] += f;
  context->state[6] += g; context->state[7] += h;
}

static void sha256_initialize(sha256_context *context) {
  static const uint32_t initial[8] = {
      0x6a09e667u, 0xbb67ae85u, 0x3c6ef372u, 0xa54ff53au,
      0x510e527fu, 0x9b05688cu, 0x1f83d9abu, 0x5be0cd19u,
  };
  memcpy(context->state, initial, sizeof(initial));
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
  uint64_t original = context->bit_count;
  unsigned char marker = 0x80;
  unsigned char zero = 0;
  unsigned char length[8];
  int index;
  sha256_update(context, &marker, 1);
  while (context->block_bytes != 56) {
    sha256_update(context, &zero, 1);
  }
  for (index = 0; index < 8; ++index) {
    length[7 - index] = (unsigned char)(original >> (8 * index));
  }
  sha256_update(context, length, sizeof(length));
  for (index = 0; index < 8; ++index) {
    int byte_index;
    for (byte_index = 0; byte_index < 4; ++byte_index) {
      digest[4 * index + byte_index] =
          (unsigned char)(context->state[index] >> (24 - 8 * byte_index));
    }
  }
}

static void digest_to_hex(const unsigned char digest[32], char output[65]) {
  static const char digits[] = "0123456789abcdef";
  int index;
  for (index = 0; index < 32; ++index) {
    output[2 * index] = digits[digest[index] >> 4];
    output[2 * index + 1] = digits[digest[index] & 15];
  }
  output[64] = '\0';
}

static int valid_sha256(const char *value) {
  size_t index;
  if (value == NULL || strlen(value) != 64) return 0;
  for (index = 0; index < 64; ++index) {
    if (!((value[index] >= '0' && value[index] <= '9') ||
          (value[index] >= 'a' && value[index] <= 'f'))) return 0;
  }
  return 1;
}

static int fail(const char *message) {
  (void)!write(STDERR_FILENO, message, strlen(message));
  (void)!write(STDERR_FILENO, "\n", 1);
  return FAILURE_EXIT;
}

static int same_identity(const struct stat *left, const struct stat *right) {
  return left->st_dev == right->st_dev && left->st_ino == right->st_ino &&
         left->st_mode == right->st_mode && left->st_nlink == right->st_nlink &&
         left->st_uid == right->st_uid && left->st_gid == right->st_gid &&
         left->st_size == right->st_size &&
         left->st_mtim.tv_sec == right->st_mtim.tv_sec &&
         left->st_mtim.tv_nsec == right->st_mtim.tv_nsec &&
         left->st_ctim.tv_sec == right->st_ctim.tv_sec &&
         left->st_ctim.tv_nsec == right->st_ctim.tv_nsec;
}

static int verify_directory_fd(int descriptor, mode_t mode, uid_t uid,
                               gid_t gid, int exact_links,
                               struct stat *result) {
  struct stat metadata;
  if (fstat(descriptor, &metadata) != 0 || !S_ISDIR(metadata.st_mode) ||
      (metadata.st_mode & 07777) != mode || metadata.st_uid != uid ||
      metadata.st_gid != gid ||
      (exact_links >= 0 && metadata.st_nlink != (nlink_t)exact_links)) {
    return -1;
  }
  if (result != NULL) *result = metadata;
  return 0;
}

static int verify_regular_fd(int descriptor, mode_t mode, uid_t uid,
                             gid_t gid, off_t exact_size,
                             struct stat *result) {
  struct stat metadata;
  if (fstat(descriptor, &metadata) != 0 || !S_ISREG(metadata.st_mode) ||
      metadata.st_nlink != 1 || (metadata.st_mode & 07777) != mode ||
      metadata.st_uid != uid || metadata.st_gid != gid ||
      (exact_size >= 0 && metadata.st_size != exact_size) ||
      (metadata.st_size > 0 && metadata.st_blocks * 512 < metadata.st_size)) {
    return -1;
  }
  if (result != NULL) *result = metadata;
  return 0;
}

static int hash_fd(int descriptor, const file_pin *expected) {
  unsigned char buffer[COPY_CHUNK_BYTES];
  unsigned char digest[32];
  char hexadecimal[65];
  sha256_context context;
  off_t total = 0;
  ssize_t observed;
  if (expected->size_bytes <= 0 || expected->size_bytes > MAX_PINNED_BYTES ||
      !valid_sha256(expected->sha256) || lseek(descriptor, 0, SEEK_SET) < 0) {
    return -1;
  }
  sha256_initialize(&context);
  while (total < expected->size_bytes) {
    size_t remaining = (size_t)(expected->size_bytes - total);
    size_t wanted = remaining < sizeof(buffer) ? remaining : sizeof(buffer);
    observed = read(descriptor, buffer, wanted);
    if (observed <= 0 || observed > expected->size_bytes - total) return -1;
    sha256_update(&context, buffer, (size_t)observed);
    total += observed;
  }
  if (read(descriptor, buffer, 1) != 0 || lseek(descriptor, 0, SEEK_SET) < 0)
    return -1;
  sha256_finalize(&context, digest);
  digest_to_hex(digest, hexadecimal);
  return total == expected->size_bytes &&
                 strcmp(hexadecimal, expected->sha256) == 0
             ? 0
             : -1;
}

static int open_parent_nofollow(const char *path, int *parent_result,
                                char name_result[NAME_MAX + 1]) {
  char copy[PATH_MAX];
  size_t length, cursor = 1;
  int current;
  if (path == NULL || path[0] != '/' || path[1] == '\0') return -1;
  length = strlen(path);
  if (length >= sizeof(copy) || path[length - 1] == '/') return -1;
  memcpy(copy, path, length + 1);
  current = open("/", O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
  if (current < 0) return -1;
  while (cursor < length) {
    size_t start = cursor;
    size_t component_length;
    int is_last, next;
    while (cursor < length && copy[cursor] != '/') ++cursor;
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

static int open_directory_path(const char *path, mode_t mode, uid_t uid,
                               gid_t gid, int links, struct stat *metadata) {
  char name[NAME_MAX + 1];
  int parent, descriptor;
  if (open_parent_nofollow(path, &parent, name) != 0) return -1;
  descriptor = openat(parent, name,
                      O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
  (void)close(parent);
  if (descriptor < 0 ||
      verify_directory_fd(descriptor, mode, uid, gid, links, metadata) != 0) {
    if (descriptor >= 0) (void)close(descriptor);
    return -1;
  }
  return descriptor;
}

static int exact_inventory(int descriptor, held_file *files,
                           size_t file_count) {
  unsigned char seen[4] = {0, 0, 0, 0};
  int duplicate = openat(descriptor, ".",
                         O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
  DIR *stream;
  struct dirent *entry;
  size_t observed = 0;
  if (file_count > 4 || duplicate < 0) return -1;
  stream = fdopendir(duplicate);
  if (stream == NULL) {
    (void)close(duplicate);
    return -1;
  }
  errno = 0;
  while ((entry = readdir(stream)) != NULL) {
    size_t index;
    int matched = 0;
    if (strcmp(entry->d_name, ".") == 0 || strcmp(entry->d_name, "..") == 0)
      continue;
    for (index = 0; index < file_count; ++index) {
      if (!seen[index] && strcmp(entry->d_name, files[index].name) == 0) {
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
  if (errno != 0 || closedir(stream) != 0 || observed != file_count)
    return -1;
  return 0;
}

static int open_tree(held_tree *tree) {
  size_t index;
  tree->descriptor = open_directory_path(tree->path, tree->mode, tree->uid,
                                         tree->gid, 2, &tree->metadata);
  if (tree->descriptor < 0 ||
      exact_inventory(tree->descriptor, tree->files, tree->file_count) != 0)
    return -1;
  for (index = 0; index < tree->file_count; ++index) {
    held_file *file = &tree->files[index];
    file->descriptor = openat(tree->descriptor, file->name,
                              O_RDONLY | O_NONBLOCK | O_NOFOLLOW | O_CLOEXEC);
    if (file->descriptor < 0 ||
        verify_regular_fd(file->descriptor, file->mode, file->uid, file->gid,
                          file->pin.size_bytes, &file->metadata) != 0 ||
        (file->pin.size_bytes > 0 && hash_fd(file->descriptor, &file->pin) != 0))
      return -1;
  }
  return 0;
}

static void close_tree(held_tree *tree) {
  size_t index;
  for (index = 0; index < tree->file_count; ++index) {
    if (tree->files[index].descriptor >= 0) {
      (void)close(tree->files[index].descriptor);
      tree->files[index].descriptor = -1;
    }
  }
  if (tree->descriptor >= 0) {
    (void)close(tree->descriptor);
    tree->descriptor = -1;
  }
}

static int revalidate_tree(held_tree *tree) {
  struct stat current, reopened_info;
  int reopened;
  size_t index;
  if (verify_directory_fd(tree->descriptor, tree->mode, tree->uid, tree->gid,
                          2, &current) != 0 ||
      !same_identity(&tree->metadata, &current) ||
      exact_inventory(tree->descriptor, tree->files, tree->file_count) != 0)
    return -1;
  reopened = open_directory_path(tree->path, tree->mode, tree->uid, tree->gid,
                                 2, &reopened_info);
  if (reopened < 0 || !same_identity(&tree->metadata, &reopened_info) ||
      exact_inventory(reopened, tree->files, tree->file_count) != 0) {
    if (reopened >= 0) (void)close(reopened);
    return -1;
  }
  for (index = 0; index < tree->file_count; ++index) {
    held_file *file = &tree->files[index];
    struct stat held_info, reopened_file_info;
    int reopened_file;
    if (verify_regular_fd(file->descriptor, file->mode, file->uid, file->gid,
                          file->pin.size_bytes, &held_info) != 0 ||
        !same_identity(&file->metadata, &held_info) ||
        (file->pin.size_bytes > 0 && hash_fd(file->descriptor, &file->pin) != 0)) {
      (void)close(reopened);
      return -1;
    }
    reopened_file = openat(reopened, file->name,
                           O_RDONLY | O_NONBLOCK | O_NOFOLLOW | O_CLOEXEC);
    if (reopened_file < 0 ||
        verify_regular_fd(reopened_file, file->mode, file->uid, file->gid,
                          file->pin.size_bytes, &reopened_file_info) != 0 ||
        !same_identity(&file->metadata, &reopened_file_info) ||
        (file->pin.size_bytes > 0 && hash_fd(reopened_file, &file->pin) != 0)) {
      if (reopened_file >= 0) (void)close(reopened_file);
      (void)close(reopened);
      return -1;
    }
    (void)close(reopened_file);
  }
  (void)close(reopened);
  return 0;
}

static int path_absent_at(int parent, const char *name) {
  struct stat metadata;
  errno = 0;
  return fstatat(parent, name, &metadata, AT_SYMLINK_NOFOLLOW) < 0 &&
                 errno == ENOENT
             ? 0
             : -1;
}

static int rename_noreplace(int parent, const char *source,
                            const char *destination) {
  return (int)syscall(SYS_renameat2, parent, source, parent, destination,
                      RENAME_NOREPLACE);
}

static int write_all(int descriptor, const unsigned char *buffer, size_t size) {
  size_t total = 0;
  while (total < size) {
    ssize_t written = write(descriptor, buffer + total, size - total);
    if (written <= 0) return -1;
    total += (size_t)written;
  }
  return 0;
}

static int copy_held_file(const held_file *source, int destination_root,
                          const char *destination_name, mode_t final_mode) {
  unsigned char buffer[COPY_CHUNK_BYTES];
  off_t total = 0;
  int destination = openat(destination_root, destination_name,
                           O_RDWR | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC,
                           0600);
  if (destination < 0 || lseek(source->descriptor, 0, SEEK_SET) < 0) {
    if (destination >= 0) (void)close(destination);
    return -1;
  }
  while (total < source->pin.size_bytes) {
    size_t remaining = (size_t)(source->pin.size_bytes - total);
    size_t wanted = remaining < sizeof(buffer) ? remaining : sizeof(buffer);
    ssize_t observed = read(source->descriptor, buffer, wanted);
    if (observed <= 0 || write_all(destination, buffer, (size_t)observed) != 0) {
      (void)close(destination);
      return -1;
    }
    total += observed;
  }
  if (read(source->descriptor, buffer, 1) != 0 ||
      lseek(source->descriptor, 0, SEEK_SET) < 0 ||
      fchown(destination, ROOT_UID, ROOT_GID) != 0 ||
      fchmod(destination, final_mode) != 0 || fsync(destination) != 0 ||
      hash_fd(destination, &source->pin) != 0) {
    (void)close(destination);
    return -1;
  }
  (void)close(destination);
  return total == source->pin.size_bytes ? 0 : -1;
}

static int create_lock(int destination_root) {
  int descriptor = openat(destination_root, LOCK_NAME,
                          O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC,
                          0600);
  if (descriptor < 0 || fchown(descriptor, ROOT_UID, ROOT_GID) != 0 ||
      fchmod(descriptor, FINAL_LOCK_MODE) != 0 || fsync(descriptor) != 0) {
    if (descriptor >= 0) (void)close(descriptor);
    return -1;
  }
  (void)close(descriptor);
  return 0;
}

static int sync_and_revalidate_tree(held_tree *tree) {
  size_t index;
  for (index = 0; index < tree->file_count; ++index) {
    if (fsync(tree->files[index].descriptor) != 0) return -1;
  }
  if (fsync(tree->descriptor) != 0) return -1;
  return revalidate_tree(tree);
}

static void initialize_final(held_tree *tree, held_file files[4]);

static int audit_final_directory_fd(int descriptor) {
  held_file files[4];
  held_tree unused;
  size_t index;
  initialize_final(&unused, files);
  if (verify_directory_fd(descriptor, SEALED_DIRECTORY_MODE, ROOT_UID,
                          ROOT_GID, 2, NULL) != 0 ||
      exact_inventory(descriptor, files, 4) != 0)
    return -1;
  for (index = 0; index < 4; ++index) {
    int file = openat(descriptor, files[index].name,
                      O_RDONLY | O_NONBLOCK | O_NOFOLLOW | O_CLOEXEC);
    if (file < 0 ||
        verify_regular_fd(file, files[index].mode, ROOT_UID, ROOT_GID,
                          files[index].pin.size_bytes, NULL) != 0 ||
        (files[index].pin.size_bytes > 0 &&
         hash_fd(file, &files[index].pin) != 0)) {
      if (file >= 0) (void)close(file);
      return -1;
    }
    (void)close(file);
  }
  return 0;
}

static int revalidate_root_parent(int descriptor,
                                  const struct stat *held_metadata) {
  struct stat current, reopened_info;
  int reopened;
  if (verify_directory_fd(descriptor, PRIVATE_DIRECTORY_MODE, ROOT_UID,
                          ROOT_GID, -1, &current) != 0 ||
      held_metadata->st_dev != current.st_dev ||
      held_metadata->st_ino != current.st_ino)
    return -1;
  reopened = open_directory_path(ROOT_PARENT, PRIVATE_DIRECTORY_MODE,
                                 ROOT_UID, ROOT_GID, -1, &reopened_info);
  if (reopened < 0 || held_metadata->st_dev != reopened_info.st_dev ||
      held_metadata->st_ino != reopened_info.st_ino) {
    if (reopened >= 0) (void)close(reopened);
    return -1;
  }
  (void)close(reopened);
  return 0;
}

#ifdef VISTA_R8_INITIAL_INSTALLER_TESTING
static int test_failure_point(const char *label) {
  const char *selected = getenv("VISTA_R8_INITIAL_INSTALLER_FAILPOINT");
  return selected != NULL && strcmp(selected, label) == 0 ? -1 : 0;
}

static void test_pause_at(const char *label) {
  const char *selected = getenv("VISTA_R8_INITIAL_INSTALLER_PAUSE_POINT");
  const char *value = getenv("VISTA_R8_INITIAL_INSTALLER_PAUSE_US");
  const char *ready_path;
  if ((selected == NULL && strcmp(label, "after_candidate_open") != 0) ||
      (selected != NULL && strcmp(selected, label) != 0))
    return;
  ready_path = getenv("VISTA_R8_INITIAL_INSTALLER_PAUSE_READY_PATH");
  if (ready_path != NULL) {
    int ready = open(ready_path,
                     O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC,
                     0600);
    if (ready >= 0) {
      (void)!write(ready, "ready\n", 6);
      (void)close(ready);
    }
  }
  if (value != NULL) {
    char *end = NULL;
    unsigned long delay = strtoul(value, &end, 10);
    if (end != value && *end == '\0' && delay <= 5000000ul) usleep(delay);
  }
}
#else
static int test_failure_point(const char *label) {
  (void)label;
  return 0;
}
static void test_pause_at(const char *label) { (void)label; }
#endif

static int cleanup_private_staging(int parent, const char *name, int staging) {
  static const char *const names[] = {
      LAUNCHER_NAME, HELPER_NAME, INPUT_NAME, LOCK_NAME,
  };
  struct stat current, path_info, final_held_info;
  size_t index;
  if (fstat(staging, &current) != 0 || !S_ISDIR(current.st_mode) ||
      current.st_nlink != 2 || current.st_uid != ROOT_UID ||
      current.st_gid != ROOT_GID ||
      ((current.st_mode & 07777) != PRIVATE_DIRECTORY_MODE &&
       (current.st_mode & 07777) != SEALED_DIRECTORY_MODE) ||
      fstatat(parent, name, &path_info, AT_SYMLINK_NOFOLLOW) != 0 ||
      !same_identity(&current, &path_info) ||
      fchmod(staging, PRIVATE_DIRECTORY_MODE) != 0 ||
      verify_directory_fd(staging, PRIVATE_DIRECTORY_MODE, ROOT_UID, ROOT_GID,
                          2, NULL) != 0)
    return -1;
  for (index = 0; index < 4; ++index) {
    if (unlinkat(staging, names[index], 0) != 0 && errno != ENOENT) return -1;
  }
  if (fsync(staging) != 0) return -1;
  test_pause_at("before_cleanup_final_rebind");
  if (verify_directory_fd(staging, PRIVATE_DIRECTORY_MODE, ROOT_UID, ROOT_GID,
                          2, &final_held_info) != 0 ||
      fstatat(parent, name, &path_info, AT_SYMLINK_NOFOLLOW) != 0 ||
      !same_identity(&final_held_info, &path_info) ||
      unlinkat(parent, name, AT_REMOVEDIR) != 0 || fsync(parent) != 0 ||
      close(staging) != 0)
    return -1;
  return 0;
}

static int cleanup_unopened_private_staging(
    int parent, const char *name, const struct stat *created) {
  struct stat current, path_info;
  int staging;
  if (created == NULL || !S_ISDIR(created->st_mode) || created->st_nlink != 2 ||
      created->st_uid != ROOT_UID || created->st_gid != ROOT_GID ||
      (created->st_mode & 07777) != PRIVATE_DIRECTORY_MODE)
    return -1;
  staging = openat(parent, name,
                   O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
  if (staging < 0) return -1;
  if (verify_directory_fd(staging, PRIVATE_DIRECTORY_MODE, ROOT_UID, ROOT_GID,
                          2, &current) != 0 ||
      !same_identity(created, &current)) {
    (void)close(staging);
    return -1;
  }
  test_pause_at("before_cleanup_final_rebind");
  if (verify_directory_fd(staging, PRIVATE_DIRECTORY_MODE, ROOT_UID, ROOT_GID,
                          2, &current) != 0 ||
      fstatat(parent, name, &path_info, AT_SYMLINK_NOFOLLOW) != 0 ||
      !same_identity(&current, &path_info) ||
      unlinkat(parent, name, AT_REMOVEDIR) != 0 || fsync(parent) != 0 ||
      close(staging) != 0)
    return -1;
  return 0;
}

static void initialize_candidate(held_tree *tree, held_file files[3]) {
  files[0] = (held_file){
      .name = LAUNCHER_NAME,
      .mode = CANDIDATE_LAUNCHER_MODE,
      .uid = REVIEW_UID,
      .gid = REVIEW_GID,
      .pin = {.sha256 = EXPECTED_LAUNCHER_SHA256,
              .size_bytes = EXPECTED_LAUNCHER_SIZE},
      .descriptor = -1,
      .metadata = {0},
  };
  files[1] = (held_file){
      .name = HELPER_NAME,
      .mode = CANDIDATE_DATA_MODE,
      .uid = REVIEW_UID,
      .gid = REVIEW_GID,
      .pin = {.sha256 = EXPECTED_HELPER_SHA256,
              .size_bytes = EXPECTED_HELPER_SIZE},
      .descriptor = -1,
      .metadata = {0},
  };
  files[2] = (held_file){
      .name = INPUT_NAME,
      .mode = CANDIDATE_DATA_MODE,
      .uid = REVIEW_UID,
      .gid = REVIEW_GID,
      .pin = {.sha256 = EXPECTED_INPUT_PIN_SHA256,
              .size_bytes = EXPECTED_INPUT_PIN_SIZE},
      .descriptor = -1,
      .metadata = {0},
  };
  *tree = (held_tree){CANDIDATE_ROOT, REVIEW_UID, REVIEW_GID,
                      SEALED_DIRECTORY_MODE, files, 3, -1, {0}};
}

static void initialize_final(held_tree *tree, held_file files[4]) {
  files[0] = (held_file){
      .name = LAUNCHER_NAME,
      .mode = FINAL_LAUNCHER_MODE,
      .uid = ROOT_UID,
      .gid = ROOT_GID,
      .pin = {.sha256 = EXPECTED_LAUNCHER_SHA256,
              .size_bytes = EXPECTED_LAUNCHER_SIZE},
      .descriptor = -1,
      .metadata = {0},
  };
  files[1] = (held_file){
      .name = HELPER_NAME,
      .mode = FINAL_HELPER_MODE,
      .uid = ROOT_UID,
      .gid = ROOT_GID,
      .pin = {.sha256 = EXPECTED_HELPER_SHA256,
              .size_bytes = EXPECTED_HELPER_SIZE},
      .descriptor = -1,
      .metadata = {0},
  };
  files[2] = (held_file){
      .name = INPUT_NAME,
      .mode = FINAL_INPUT_MODE,
      .uid = ROOT_UID,
      .gid = ROOT_GID,
      .pin = {.sha256 = EXPECTED_INPUT_PIN_SHA256,
              .size_bytes = EXPECTED_INPUT_PIN_SIZE},
      .descriptor = -1,
      .metadata = {0},
  };
  files[3] = (held_file){
      .name = LOCK_NAME,
      .mode = FINAL_LOCK_MODE,
      .uid = ROOT_UID,
      .gid = ROOT_GID,
      .pin = {.sha256 = "", .size_bytes = 0},
      .descriptor = -1,
      .metadata = {0},
  };
  *tree = (held_tree){FINAL_ROOT, ROOT_UID, ROOT_GID,
                      SEALED_DIRECTORY_MODE, files, 4, -1, {0}};
}

static int audit_final(int sync_files, const struct stat *expected_identity) {
  held_file files[4];
  held_tree tree;
  int result;
  initialize_final(&tree, files);
  if (open_tree(&tree) != 0) {
    close_tree(&tree);
    return -1;
  }
  if (expected_identity != NULL &&
      !same_identity(expected_identity, &tree.metadata)) {
    close_tree(&tree);
    return -1;
  }
  result = sync_files ? sync_and_revalidate_tree(&tree) : revalidate_tree(&tree);
  close_tree(&tree);
  return result;
}

static int final_path_matches_promoted_staging(
    int parent, const char *name, int staging,
    const struct stat *promoted_identity) {
  struct stat held_info, path_info;
  if (promoted_identity == NULL ||
      verify_directory_fd(staging, SEALED_DIRECTORY_MODE, ROOT_UID, ROOT_GID,
                          2, &held_info) != 0 ||
      !same_identity(promoted_identity, &held_info) ||
      fstatat(parent, name, &path_info, AT_SYMLINK_NOFOLLOW) != 0 ||
      !same_identity(&held_info, &path_info))
    return -1;
  return 0;
}

int main(int argc, char **argv) {
  held_file self_files[1];
  held_file candidate_files[3];
  held_tree self_tree, candidate_tree;
  struct stat live_self_info, parent_info, staging_info, created_staging_info;
  struct stat promoted_staging_info;
  int live_self = -1, parent = -1, staging = -1;
  int is_reconcile = 0, renamed = 0, rename_outcome_uncertain = 0;
  int created_staging_valid = 0;
  char staging_name[NAME_MAX + 1];
  const char *acknowledgement;

  if (argc != 3)
    return fail("R8_INITIAL_INSTALLER: exactly operation and acknowledgement required");
  if (strcmp(argv[1], INSTALL_OPERATION) == 0) {
    acknowledgement = INSTALL_ACK;
  } else if (strcmp(argv[1], RECONCILE_OPERATION) == 0) {
    acknowledgement = RECONCILE_ACK;
    is_reconcile = 1;
  } else {
    return fail("R8_INITIAL_INSTALLER: operation differs");
  }
  if (strcmp(argv[2], acknowledgement) != 0)
    return fail("R8_INITIAL_INSTALLER: acknowledgement differs");
  if (geteuid() != REQUIRED_EUID || getegid() != REQUIRED_EGID)
    return fail("R8_INITIAL_INSTALLER: required EUID or EGID differs");
  if (!valid_sha256(EXPECTED_LAUNCHER_SHA256) ||
      !valid_sha256(EXPECTED_HELPER_SHA256) ||
      !valid_sha256(EXPECTED_INPUT_PIN_SHA256))
    return fail("R8_INITIAL_INSTALLER: compiled pin differs");

  self_files[0] = (held_file){
      .name = INSTALLER_NAME,
      .mode = INSTALLER_MODE,
      .uid = ROOT_UID,
      .gid = ROOT_GID,
      .pin = {.sha256 = "", .size_bytes = 0},
      .descriptor = -1,
      .metadata = {0},
  };
  self_tree = (held_tree){SELF_ROOT, ROOT_UID, ROOT_GID,
                          SEALED_DIRECTORY_MODE, self_files, 1, -1, {0}};
  /* Self has no embedded self hash: the independently conveyed binary pin is
   * the finite manual ceremony.  Exact live identity prevents copied bypasses. */
  self_files[0].pin.size_bytes = -1;
  if (open_tree(&self_tree) != 0)
    return fail("R8_INITIAL_INSTALLER: installed self authority differs");
  live_self = open("/proc/self/exe", O_RDONLY | O_NONBLOCK | O_CLOEXEC);
  if (live_self < 0 ||
      verify_regular_fd(live_self, INSTALLER_MODE, ROOT_UID, ROOT_GID, -1,
                        &live_self_info) != 0 ||
      !same_identity(&self_files[0].metadata, &live_self_info))
    return fail("R8_INITIAL_INSTALLER: live self differs");
  parent = open_directory_path(ROOT_PARENT, PRIVATE_DIRECTORY_MODE,
                               ROOT_UID, ROOT_GID, -1, &parent_info);
  if (parent < 0 || fsync(self_files[0].descriptor) != 0 ||
      fsync(self_tree.descriptor) != 0 || fsync(parent) != 0 ||
      revalidate_tree(&self_tree) != 0)
    return fail("R8_INITIAL_INSTALLER: self durability reconciliation failed");

  if (is_reconcile) {
    if (audit_final(1, NULL) != 0 || fsync(parent) != 0 ||
        audit_final(0, NULL) != 0)
      return fail("R8_INITIAL_INSTALLER: reconcile final authority differs");
    (void)!write(STDOUT_FILENO, "reconciled-initial-bootstrap\n", 29);
    return 0;
  }

  if (path_absent_at(parent, strrchr(FINAL_ROOT, '/') + 1) != 0)
    return fail("R8_INITIAL_INSTALLER: final path is not fresh");
  initialize_candidate(&candidate_tree, candidate_files);
  if (open_tree(&candidate_tree) != 0)
    return fail("R8_INITIAL_INSTALLER: reviewed candidate differs");
  test_pause_at("after_candidate_open");
  if (revalidate_tree(&candidate_tree) != 0 ||
      path_absent_at(parent, strrchr(FINAL_ROOT, '/') + 1) != 0)
    return fail("R8_INITIAL_INSTALLER: candidate drifted before staging");

  if (snprintf(staging_name, sizeof(staging_name),
               ".vista-r8-ue57-initial-bootstrap.staging-%ld", (long)getpid()) < 0 ||
      mkdirat(parent, staging_name, PRIVATE_DIRECTORY_MODE) != 0)
    return fail("R8_INITIAL_INSTALLER: private staging creation failed");
  if (fstatat(parent, staging_name, &created_staging_info,
              AT_SYMLINK_NOFOLLOW) != 0 ||
      !S_ISDIR(created_staging_info.st_mode) ||
      created_staging_info.st_nlink != 2 ||
      created_staging_info.st_uid != ROOT_UID ||
      created_staging_info.st_gid != ROOT_GID ||
      (created_staging_info.st_mode & 07777) != PRIVATE_DIRECTORY_MODE)
    goto install_failure;
  created_staging_valid = 1;
  test_pause_at("after_staging_identity");
  if (test_failure_point("before_staging_open") != 0) goto install_failure;
  staging = openat(parent, staging_name,
                   O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
  if (staging < 0) goto install_failure;
  if (verify_directory_fd(staging, PRIVATE_DIRECTORY_MODE, ROOT_UID, ROOT_GID,
                          2, &staging_info) != 0 ||
      !same_identity(&created_staging_info, &staging_info)) {
    (void)close(staging);
    staging = -1;
    goto install_failure;
  }
  if (copy_held_file(&candidate_files[0], staging, LAUNCHER_NAME,
                     FINAL_LAUNCHER_MODE) != 0 ||
      revalidate_tree(&candidate_tree) != 0 ||
      copy_held_file(&candidate_files[1], staging, HELPER_NAME,
                     FINAL_HELPER_MODE) != 0 ||
      revalidate_tree(&candidate_tree) != 0 ||
      copy_held_file(&candidate_files[2], staging, INPUT_NAME,
                     FINAL_INPUT_MODE) != 0 ||
      create_lock(staging) != 0 || revalidate_tree(&candidate_tree) != 0 ||
      fchmod(staging, SEALED_DIRECTORY_MODE) != 0 || fsync(staging) != 0 ||
      audit_final_directory_fd(staging) != 0 ||
      revalidate_tree(&candidate_tree) != 0 ||
      revalidate_root_parent(parent, &parent_info) != 0 ||
      path_absent_at(parent, strrchr(FINAL_ROOT, '/') + 1) != 0 ||
      test_failure_point("before_rename") != 0)
    goto install_failure;
  if (rename_noreplace(parent, staging_name, strrchr(FINAL_ROOT, '/') + 1) != 0)
    goto install_failure;
  rename_outcome_uncertain = 1;
  /* Test-only hook models an ambiguous syscall report after namespace
   * promotion but before the local renamed flag can be trusted.  Cleanup must
   * prove staging_name still names the held inode before any chmod/unlink. */
  if (test_failure_point("ambiguous_rename_result") != 0)
    goto install_failure;
  renamed = 1;
  rename_outcome_uncertain = 0;
  test_pause_at("after_rename_before_reopen");
  if (test_failure_point("after_rename") != 0 ||
      test_failure_point("before_final_fsync") != 0 || fsync(staging) != 0 ||
      test_failure_point("after_final_fsync") != 0 ||
      test_failure_point("before_parent_fsync") != 0 || fsync(parent) != 0 ||
      test_failure_point("after_parent_fsync") != 0 ||
      test_failure_point("before_reopen") != 0 ||
      verify_directory_fd(staging, SEALED_DIRECTORY_MODE, ROOT_UID, ROOT_GID,
                          2, &promoted_staging_info) != 0 ||
      audit_final(0, &promoted_staging_info) != 0 ||
      test_failure_point("after_reopen") != 0)
    goto install_failure;
  test_pause_at("after_first_final_audit");
  if (revalidate_tree(&candidate_tree) != 0 ||
      revalidate_root_parent(parent, &parent_info) != 0 ||
      final_path_matches_promoted_staging(
          parent, strrchr(FINAL_ROOT, '/') + 1, staging,
          &promoted_staging_info) != 0 ||
      audit_final(0, &promoted_staging_info) != 0)
    goto install_failure;
  (void)!write(STDOUT_FILENO, "installed-initial-bootstrap\n", 28);
  return 0;

install_failure:
  if (!renamed && staging >= 0) {
    (void)cleanup_private_staging(parent, staging_name, staging);
  } else if (!renamed && created_staging_valid) {
    (void)cleanup_unopened_private_staging(parent, staging_name,
                                           &created_staging_info);
  }
  if (renamed || rename_outcome_uncertain)
    return fail("R8_INITIAL_INSTALLER: durability unknown; reconcile required");
  return fail("R8_INITIAL_INSTALLER: installation failed before rename");
}
