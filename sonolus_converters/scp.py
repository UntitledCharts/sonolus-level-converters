import json, os
import zipfile


def replace_first_level(input_scp: str, output_scp: str, leveldata_file: str):
    with zipfile.ZipFile(input_scp, "r") as z_in:
        with zipfile.ZipFile(
            output_scp, "w", compression=zipfile.ZIP_DEFLATED
        ) as z_out:
            file = None
            for item in z_in.infolist():
                if (
                    item.filename.startswith("sonolus/levels/")
                    and os.path.basename(item.filename) not in ("info", "list")
                    and not item.filename.endswith("/")
                ):
                    with z_in.open(item) as f:
                        try:
                            data = json.load(f)
                            file = data.get("item", {}).get("data")
                            break
                        except Exception:
                            continue
            if not file:
                raise KeyError("No level file found")

            for item in z_in.infolist():
                with z_in.open(item) as f:
                    if item.filename == f"sonolus/repository/{file['hash']}":
                        z_out.writestr(item, open(leveldata_file, "rb").read())
                    else:
                        z_out.writestr(item.filename, f.read())
