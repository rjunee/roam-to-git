import os
import re
from collections import defaultdict
from itertools import takewhile
from pathlib import Path
from typing import Dict, List, Match, Tuple
#from fs import note_filename
from roam_to_git.fs import note_filename
from loguru import logger

def read_markdown_directory(raw_directory: Path) -> Dict[str, str]:
    contents = {}
    for file in raw_directory.iterdir():
        if file.is_dir():
            # We recursively add the content of sub-directories.
            # They exists when there is a / in the note name.
            for child_name, content in read_markdown_directory(file).items():
                contents[f"{file.name}/{child_name}"] = content
        if not file.is_file():
            continue
        content = file.read_text(encoding="utf-8")
        parts = file.parts[len(raw_directory.parts):]
        file_name = os.path.join(*parts)
        contents[file_name] = content
    return contents


def get_back_links(contents: Dict[str, str]) -> Dict[str, List[Tuple[str, Match]]]:
    # Extract backlinks from the markdown
    forward_links = {file_name: extract_links(content) for file_name, content in contents.items()}
    back_links: Dict[str, List[Tuple[str, Match]]] = defaultdict(list)
    for file_name, links in forward_links.items():
        for link in links:
            back_links[f"{link.group(1)}.md"].append((file_name, link))
    return back_links



def fix_triple_backticks(content: str) -> str:
    return re.sub(r'- ```', r'\n```', content)

def format_markdown(contents: Dict[str, str]) -> Dict[str, str]:
    back_links = get_back_links(contents)
    # Format and write the markdown files
    out = {}
    for file_name, content in contents.items():
        # We add the backlinks first, because they use the position of the caracters
        # of the regex matchs
        content = add_back_links(content, back_links[file_name])

        # Format content. Backlinks content will be formatted automatically.
        content = format_to_do(content)
        link_prefix = "../" * sum("/" in char for char in file_name)
        content = format_link(content, link_prefix=link_prefix)
        if len(content) > 0:
            out[file_name] = content

    return out


def get_allowed_notes(dir: Path) -> List[str]:
    allowed_notes = []
    if (dir/"Garden.md").exists():
        with open(dir/"Garden.md") as f:
            for line in f:
                match = re.match(r'- \[\[(.*)\]\]', line)
                if match:
                    note_title = match.group(1)
                    allowed_notes.append(note_title)

    return allowed_notes


def format_markdown_notes(contents: Dict[str, str], notes_dir: Path, allowed_notes: List[str]) -> Dict[str, str]:
    back_links = get_back_links(contents)
    # Format and write the markdown files
    out = {}
    for file_name, content in contents.items():
        if file_name[:-3] in allowed_notes:
            content = remove_toplevel_bullets(content)
            # We add the backlinks first, because they use the position of the caracters
            # of the regex matchs
            content = add_back_links_notes(content, notes_dir, file_name, back_links[file_name])

            # Format content. Backlinks content will be formatted automatically.
            content = format_to_do(content)
            content = extract_featured_image(content)
            content = clean_or(content)
            content = youtube_embed(content)
            link_prefix = "../" * sum("/" in char for char in file_name)
            content = format_link(content, link_prefix=link_prefix)
            content = convert_links(content)
            if len(content) > 0:
                out[file_name] = content

    return out


def format_to_do(contents: str):
    contents = re.sub(r"{{\[\[TODO\]\]}} *", r"[ ] ", contents)
    contents = re.sub(r"{{\[\[DONE\]\]}} *", r"[x] ", contents)
    return contents


# Take a note-image attribute and convert to featured_image frontmatter for jekyll theme
def extract_featured_image(contents: str):
    # match - **[note-image](/note-image-79f375){: .internal-link}:** https://unsplash.com/photos/A57akxc-4BQ
    # output in front matter https://source.unsplash.com/A57akxc-4BQ/800x300
    # TODO update image size based on template (or leave size out here and let the template do it?)
    image_found = re.search(r"note\-image\:\:.*https\:\/\/unsplash\.com\/photos\/(A57akxc-4BQ)", contents)
    if image_found:
        # Strip meta tag
        contents = re.sub(r"note\-image\:\:.*https\:\/\/unsplash\.com\/photos\/.*", '', contents)
        # Add to frontmatter
        contents = re.sub(r"^---\ntitle\:", "---\nfeatured_image: 'https://source.unsplash.com/" + image_found.group(1) + "/800x300'\ntitle:", contents)
        #logger.info(contents)
    return contents


# Replace Roam OR options with just the selected (first) option so it doesn't get interpreted as liquid syntax
def clean_or(contents: str):
    or_found = re.search(r"\{\{or\:(.*?) \|(.*)\}\}", contents)
    if or_found:
        contents = re.sub(r"\{\{or\:(.*)\}\}", or_found.group(1), contents)
    return contents

# Replace YouTube embeds
def youtube_embed(contents: str):
    yt_found = re.search(r"\{\{youtube\: http(.*)\/(.*)\}\}", contents)
    if yt_found:
        contents = re.sub(r"\{\{youtube\: http(.*)\/(.*)\}\}", '\n<iframe width="560" height="315" src="https://www.youtube.com/embed/' + yt_found.group(2) + '" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe>', contents)
    return contents

# Remove top level bullets so it looks more like an article less like Roam
# TODO This function is from Manoj on Fiverr.  Not the best code, should be refactored
def remove_toplevel_bullets(contents: str):
    lines = contents.splitlines()
    is_last_one_bullet=False
    is_heading_list=[False, False, False, False]
    new_contents = ""

    for i in range(0,len(lines)):
        edited_line = ""
        if lines[i]=="" or lines[i]==" " or lines[i]=="  " or lines[i]=="   " or lines[i]=="    ":
            continue

        if lines[i][0] == "-":
            if('#' in lines[i][2:].split(" ")[0]):
                is_heading_list[0]=True
            else:
                is_heading_list[0] = False
            edited_line="\n"+lines[i][2:]

        elif lines[i][0:5] == "    -":
            if('#' in lines[i][6:].split(" ")[0]):
                is_heading_list[1] = True
                edited_line="\n"+lines[i][6:]
            elif(is_heading_list[0]):
                is_heading_list[1] = False
                edited_line="\n"+lines[i][6:]
            else:
                is_heading_list[1] = False
                edited_line = lines[i][4:]

        elif lines[i][0:9] == "        -":
            if('#' in lines[i][10:].split(" ")[0]):
                is_heading_list[2] = True
                edited_line="\n"+lines[i][10:]
            elif(is_heading_list[1]):
                is_heading_list[2] = False
                edited_line="\n"+lines[i][10:]
            else:
                is_heading_list[2] = False
                if(is_heading_list[:3]==[False,False,False]):
                    edited_line="    "
                edited_line += lines[i][8:]

        elif lines[i][0:13] == "            -":
            if('#' in lines[i][14:].split(" ")[0]):
                is_heading_list[3] = True
                edited_line="\n"+lines[i][14:]
            elif(is_heading_list[2]):
                is_heading_list[3] = False
                edited_line="\n"+lines[i][14:]
            else:
                is_heading_list[3] = False
                if(is_heading_list[:4]==[False,False,False,False]):
                    edited_line="        "
                elif(is_heading_list[1:4]==[False,False,False]):
                    edited_line = "    "
                edited_line += lines[i][12:]

        else:
            edited_line=lines[i]

        new_contents += edited_line + "\n"

    return new_contents


def extract_links(string: str) -> List[Match]:
    out = list(re.finditer(r"\[\["
                           r"([^\]\n]+)"
                           r"\]\]", string)) + \
          list(re.finditer(r"#"
                           r"([^\], \n]+)"
                           r"[, ]", string))
    # Match attributes
    out.extend(re.finditer(r"(?:^|\n) *- "
                           r"((?:[^:\n]|:[^:\n])+)"  # Match everything except ::
                           r"::", string))
    return out


def add_back_links(content: str, back_links: List[Tuple[str, Match]]) -> str:
    if not back_links:
        return content
    files = sorted(set((file_name[:-3], match) for file_name, match in back_links),
                   key=lambda e: (e[0], e[1].start()))
    new_lines = []
    file_before = None
    for file, match in files:
        if file != file_before:
            new_lines.append(f"## [{file}](<{file}.md>)")
        file_before = file

        start_context_ = list(takewhile(lambda c: c != "\n", match.string[:match.start()][::-1]))
        start_context = "".join(start_context_[::-1])

        middle_context = match.string[match.start():match.end()]

        end_context_ = takewhile(lambda c: c != "\n", match.string[match.end()])
        end_context = "".join(end_context_)

        context = (start_context + middle_context + end_context).strip()
        new_lines.extend([context, ""])
    backlinks_str = "\n".join(new_lines)
    return f"{content}\n# Backlinks\n{backlinks_str}\n"

def add_back_links_notes(content: str, notes_dir: Path, file_name: str, back_links: List[Tuple[str, Match]]) -> str:
    if not back_links:
        return content
    files = sorted(set((file_name[:-3], match) for file_name, match in back_links),
                   key=lambda e: (e[0], e[1].start()))
    new_lines = []
    file_before = None
    for file, match in files:
        file_before = file

        start_context_ = list(takewhile(lambda c: c != "\n", match.string[:match.start()][::-1]))
        start_context = "".join(start_context_[::-1])

        middle_context = match.string[match.start():match.end()]

        end_context_ = takewhile(lambda c: c != "\n", match.string[match.end()])
        end_context = "".join(end_context_)

        context = (start_context + middle_context + end_context).strip()
        extended_context = []
        with open(notes_dir/f"{file}.md") as input:
            appending = None
            for line in input:
                if line.startswith(context) and '-' in line:
                    extended_context.append(line)
                    appending = context[0:context.index('-')+1]
                    continue
                if appending:
                    if line.startswith(appending):
                        appending = None
                    else:
                        extended_context.append(line)
        new_lines.extend(["".join(extended_context), ""])
    backlinks_str = "\n".join(new_lines)
    content = fix_triple_backticks(content)
    return f"---\ntitle: '{file_name[:-3]}'\n---\n\n{content}\n{backlinks_str}\n"


def convert_links(line: str):
    keep_looking = True
    suffix = "{: .internal-link}"
    while keep_looking:
        match = re.search(r"\(<([^>]*)>\)", line)
        if match:
            converted_link = note_filename(match.group(1))[:-3]
            converted_link = re.sub(':', '', converted_link) #strip : from links so jekyll works properly
            line = line.replace(match.group(0), f"(/{converted_link}){suffix}")
        else:
            keep_looking = False
    return line


def format_link(string: str, link_prefix="") -> str:
    """Transform a RoamResearch-like link to a Markdown link.

    @param link_prefix: Add the given prefix before all links.
        WARNING: not robust to special characters.
    """
    # Regex are read-only and can't parse [[[[recursive]] [[links]]]], but they do the job.
    # We use a special syntax for links that can have SPACES in them
    # Format internal reference: [[mynote]]
    string = re.sub(r"\[\["  # We start with [[
                    # TODO: manage a single ] in the tag
                    r"([^\]\n]+)"  # Everything except ]
                    r"\]\]",
                    rf"[\1](<{link_prefix}\1.md>)",
                    string, flags=re.MULTILINE)

    # Format hashtags: #mytag
    string = re.sub(r"#([a-zA-Z-_0-9]+)",
                    rf"[\1](<{link_prefix}\1.md>)",
                    string, flags=re.MULTILINE)

    # Format attributes
    string = re.sub(r"(^ *- )"  # Match the beginning, like '  - '
                    r"(([^:\n]|:[^:\n])+)"  # Match everything except ::
                    r"::",
                    rf"\1**[\2](<{link_prefix}\2.md>):**",  # Format Markdown link
                    string, flags=re.MULTILINE)
    return string
