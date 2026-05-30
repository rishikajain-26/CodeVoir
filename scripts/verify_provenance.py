import hashlib
import getpass

EXPECTED = "ec5d49bf469257667e3dc054623b351ac01761c868da49937fc4160f220ea1ff"


def main():
    phrase = getpass.getpass("Enter private CodeVoir proof phrase: ")
    digest = hashlib.sha256(phrase.encode("utf-8")).hexdigest()
    if digest == EXPECTED:
        print("Verified: proof phrase matches the CodeVoir provenance fingerprint.")
    else:
        print("Not verified: proof phrase does not match the provenance fingerprint.")
        print(f"Computed sha256:{digest}")


if __name__ == "__main__":
    main()
