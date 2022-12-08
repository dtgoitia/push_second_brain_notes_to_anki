## Installation

```shell
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

## Usage

1. Start Anki.
2. Run program:
  ```shell
  python -m add_and_update_note_files_to_anki \
    --root /second/brain/path
  ```

  The program will look for any file with the `.anki.md` extension (aka _note files_) inside the `/second/brain/path` directory, and upsert them into your Anki collection.

## Key info

The _note files_ must follow this format:

```txt
---
note_id: 1670503224594
deck_name: Stuff to remember
model_name: My best Note type
tags: root_topic::subtopic
---
## Question

TEST My Question _italic_ a

## Answer

My Answer **bold** and <snippet>foo = "bar"</snippet>:
<pre>
do
your
stuff
</pre>

## Source

Nice source
```

* The H2 headers will be used as the _field names_ for the _note_ . The content below each header is used as the _field value_ for the note.

* `note_id` (optional): if omitted, the program will create a new card in Anki and update the file with the ID of the newly created Note in Anki. Else, if will attempt to update an existing card, and fail if the provided `note_id` is not found in Anki.
