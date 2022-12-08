import argparse
import enum
import sys
from dataclasses import dataclass
from pathlib import Path
from pprint import pprint
from typing import Iterator

import markdown
import requests
from ankisync.ankiconnect import AnkiConnect

FieldName = str
FieldValue = str
DeckName = str
ModelName = str
Tag = str


@dataclass
class Note:
    id: int | None
    deck: DeckName
    model: ModelName
    fields: dict[FieldName, FieldValue]
    tags: set[Tag]

    def to_ankiconnect_add_note_payload(self):
        return {
            "deckName": self.deck,
            "modelName": self.model,
            "fields": self.fields,
            "tags": self.tags,
        }


def _split_raw_html_in_sections(
    raw_html: str,
) -> Iterator[tuple[FieldName, FieldValue]]:
    for item in raw_html.split("<h2>"):
        if not item:
            continue

        field_name, field_value = item.split("</h2>\n")
        if field_name == "Source":
            field_value = field_value.replace("<p>", "").replace("</p>", "")

        yield field_name.strip(), field_value.strip()


def _split_metadata_and_content(file_content: str) -> tuple[str, str]:
    _, metadata, content = file_content.split("---", maxsplit=2)
    return metadata.strip(), content.strip()


def _parse_metadata(raw: str) -> dict[str, str | list[str]]:
    metadata: dict[str, str] = {}
    for line in raw.split("\n"):
        match line.split(":", maxsplit=1):
            case [key, value]:
                key, value = key.strip(), value.strip()
                if key == "note_id":
                    metadata[key] = int(value)
                elif key == "tags":
                    metadata[key] = [s.strip() for s in value.split(",")]
                else:
                    metadata[key] = value
            case _:
                raise NotImplementedError(f"Metadata line {line!r} not understood")

    return metadata


def parse_markdown_note(path: Path) -> Note:
    file_content = path.read_text()

    raw_metadata, raw_content = _split_metadata_and_content(file_content)

    metadata = _parse_metadata(raw_metadata)

    raw_html = markdown.markdown(raw_content)
    fields = {
        field_name: field_value
        for field_name, field_value in _split_raw_html_in_sections(raw_html)
    }

    return Note(
        id=metadata.get("note_id"),
        deck=metadata["deck_name"],
        model=metadata["model_name"],
        tags=metadata["tags"],
        fields=fields,
    )


def update_note_file_id(path: Path, note_id: int) -> None:
    updated_note_id_line = f"note_id: {note_id}"
    updated_lines: list[str] = []
    id_updated = False
    for line in path.read_text().splitlines():
        if line.startswith("note_id"):
            updated_lines.append(updated_note_id_line)
            id_updated = True
        else:
            updated_lines.append(line)

    if not id_updated:
        # found Note file without "note_id" in metadata, add it straight after the
        # metadata block opening mark (aka, index 1):
        updated_lines.insert(1, updated_note_id_line)

    updated_content = "\n".join(updated_lines)
    path.write_text(updated_content)


class OperationOutcome(enum.Enum):
    insert_note = "insert_note"
    update_note = "update_note"
    file_had_id_by_note_not_in_anki = "file_had_id_by_note_not_in_anki"
    anki_gui_is_not_running = "anki_gui_is_not_running"


def upsert_note_file_in_anki_via_ankiconnect(path: Path) -> OperationOutcome:
    note = parse_markdown_note(path=path)

    anki = AnkiConnect()
    try:
        anki.version()
    except requests.exceptions.ConnectionError:
        return OperationOutcome.anki_gui_is_not_running

    if note.id is None:
        print("Adding note to Anki... ", end="")
        note_id = anki.add_note(ac_note=note.to_ankiconnect_add_note_payload())
        print("done")
        print(f"  updating {path} note file with ID {note_id}... ", end="")
        update_note_file_id(path=path, note_id=note_id)
        print("done")
        return OperationOutcome.insert_note

    else:
        print(f"Updating note {note.id}... ", end="")
        try:
            result = anki.update_note_fields(note_id=note.id, fields=note.fields)
        except ValueError as error:
            print()
            print(f"  ERROR by AnkiConnect: {error}")
            print(f"  path: {path}")
            return OperationOutcome.file_had_id_by_note_not_in_anki

        if result:
            pprint(result)
        else:
            print("done")
        return OperationOutcome.update_note


def find_note_files(root: Path) -> Iterator[Path]:
    if not root.exists():
        raise FileNotFoundError(
            f"Expected to find second brain root dir at {root}, but didn't"
        )

    _target_extension = ".anki.md"

    print(f"Finding {_target_extension!r} files in {root}\n")
    yield from root.rglob("*.anki.md")


def parse_arguments(args: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        required=True,
        help="Second brain root directory",
    )
    arguments = parser.parse_args(args)
    return arguments


def main(args: list[str] | None = None) -> str | None:
    arguments = parse_arguments(args=args)

    second_brain_root = Path(arguments.root).expanduser()

    inserted_amount = 0
    updated_amount = 0
    errored_amount = 0
    for path in find_note_files(root=second_brain_root):
        outcome = upsert_note_file_in_anki_via_ankiconnect(path=path)
        match outcome:
            case OperationOutcome.anki_gui_is_not_running:
                print(
                    "Could not connect to AnkiConnect local server. Make sure that:\n"
                    "  - Anki GUI is running\n"
                    "  - AnkiConnect plugin is installed and set up\n"
                )
                return "Program aborted"
            case OperationOutcome.insert_note:
                inserted_amount += 1
            case OperationOutcome.update_note:
                updated_amount += 1
            case OperationOutcome.file_had_id_by_note_not_in_anki:
                errored_amount += 1
            case _:
                return f"\nDid you forget to handle the outcome {outcome}?"

    print(
        "\n"
        "Summary:\n"
        f"  Notes added:    {inserted_amount}\n"
        f"  Notes updated:  {updated_amount}\n"
        f"  Errors:         {errored_amount}\n"
    )

    return None


if __name__ == "__main__":
    if exit_value := main():
        sys.exit(exit_value)
