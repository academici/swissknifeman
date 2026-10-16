"""Write the secret in argv[1] to stderr, between filler of argv[2] bytes when given."""
import sys

secret = sys.argv[1]
filler = "." * int(sys.argv[2]) if len(sys.argv) > 2 else ""
sys.stderr.write(filler + "token=" + secret + " end\n")
sys.stderr.flush()
print("{}")
