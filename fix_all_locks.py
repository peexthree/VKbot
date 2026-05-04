import os

directories = ["modules/"]

def process_file(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    lines = content.split('\n')
    new_lines = []

    in_lock = False

    for i in range(len(lines)):
        line = lines[i]
        stripped = line.strip()

        if "if not await acquire_lock(vk_id):" in stripped:
            in_lock = True

        if in_lock and stripped == "try:":
            in_lock = False

        # We need to remove the incorrect `await release_lock(vk_id)` that was added immediately after acquire_lock
        # by the previous script if it looks like:
        # if not await acquire_lock(vk_id):
        #     await release_lock(vk_id)
        #     return
        if stripped == "await release_lock(vk_id)":
            if i > 0 and "if not await acquire_lock" in lines[i-1]:
                # Skip adding this line to new_lines
                continue

        new_lines.append(line)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(new_lines))

for root, _, files in os.walk(directories[0]):
    for file in files:
        if file.endswith(".py"):
            process_file(os.path.join(root, file))
