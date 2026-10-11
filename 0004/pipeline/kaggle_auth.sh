# Source me: sets up Kaggle CLI auth from the KAGGLE_API_TOKEN secret, whatever its format.
#   - kaggle.json content ({"username":..,"key":..})  -> ~/.kaggle/kaggle.json
#   - legacy 32-hex key                                -> KAGGLE_USERNAME/KAGGLE_KEY
#   - new-style API token                              -> KAGGLE_API_TOKEN (newer kaggle CLI)
export KAGGLE_USER="${KAGGLE_USER:-mitchaelbasil}"
_T="$(printf '%s' "$KAGGLE_API_TOKEN" | tr -d '\r\n ')"
if printf '%s' "$_T" | grep -q '^{'; then
  mkdir -p ~/.kaggle && printf '%s' "$KAGGLE_API_TOKEN" > ~/.kaggle/kaggle.json && chmod 600 ~/.kaggle/kaggle.json
  KAGGLE_USER="$(python -c 'import json,os;print(json.load(open(os.path.expanduser("~/.kaggle/kaggle.json")))["username"])')"
  unset KAGGLE_API_TOKEN
elif printf '%s' "$_T" | grep -qE '^[0-9a-f]{32}$'; then
  export KAGGLE_USERNAME="$KAGGLE_USER" KAGGLE_KEY="$_T"; unset KAGGLE_API_TOKEN
else
  export KAGGLE_API_TOKEN="$_T"
fi
export KAGGLE_USER
unset _T
