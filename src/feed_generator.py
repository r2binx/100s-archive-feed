import json
from datetime import datetime, timezone
from xml.etree import ElementTree as ET

STORAGE_FILE = "data/episodes.json"
SOURCE_FILE = "data/source.xml"
RSS_TEMPLATE = "data/rss_template.xml"
OUTPUT_FEED = "docs/feed.xml"
NAMESPACES = {
    "content": "http://purl.org/rss/1.0/modules/content/",
    "dc": "http://purl.org/dc/elements/1.1/",
    "itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd",
}


def get_current_episode():
    try:
        tree = ET.parse(SOURCE_FILE)
        root = tree.getroot()
    except (FileNotFoundError, ET.ParseError) as e:
        print(f"Error reading source file: {e}")
        return None

    channel = root.find("channel")

    if channel is None:
        return None

    item = channel.find("item")

    if item is None:
        return None

    # Handle potential missing pubDate element
    pub_date_element = item.find("pubDate")
    if pub_date_element is None:
        return None

    pub_date_str = pub_date_element.text
    if not pub_date_str:  # Handle empty text content
        return None

    try:
        pub_date = datetime.strptime(pub_date_str, "%a, %d %b %Y %H:%M:%S %z")
    except ValueError:
        return None

    # Store all item data
    episode_data = {"date": pub_date.isoformat(), "elements": []}

    for elem in item:
        # Handle namespaced elements
        tag = elem.tag
        if "}" in tag:
            namespace, tag_local = tag.split("}", 1)
            namespace = namespace[1:]
        else:
            namespace = None
            tag_local = tag

        episode_data["elements"].append(
            {
                "namespace": namespace,
                "tag": tag_local,
                "text": elem.text,
                "attrib": elem.attrib,
            }
        )

    return episode_data


def update_feed(new_episode):
    try:
        with open(STORAGE_FILE, "r") as f:
            original_episodes = json.load(f)
            episodes = original_episodes.copy()
    except FileNotFoundError:
        original_episodes = {}
        episodes = {}

    now = datetime.now(timezone.utc).isoformat()
    episode_date = new_episode["date"][:10]

    # Check if we already have this exact episode
    if episode_date in episodes:
        existing_episode = episodes[episode_date]
        if existing_episode["date"] == new_episode["date"]:
            print("No new episode detected")
            return False

    # Keep only the latest episode for each day
    if episode_date in episodes:
        if new_episode["date"] > episodes[episode_date]["date"]:
            episodes[episode_date] = new_episode
    else:
        episodes[episode_date] = new_episode

    # Only write if there are changes
    if episodes == original_episodes:
        print("No changes to episodes")
        return False

    with open(STORAGE_FILE, "w") as f:
        json.dump(episodes, f, indent=2)
        print("Updated episodes.json")

    return generate_rss(episodes)


def generate_rss(episodes):
    # Load template
    tree = ET.parse(RSS_TEMPLATE)
    root = tree.getroot()
    channel = root.find("channel")

    if channel is None:
        raise ValueError("Channel not found in RSS template")

    # Register namespaces using the NAMESPACES constant
    for prefix, uri in NAMESPACES.items():
        ET.register_namespace(prefix, uri)

    # Update publication dates
    now = datetime.now(timezone.utc)
    pub_date = now.strftime("%a, %d %b %Y %H:%M:%S %z")

    for elem in ["pubDate", "lastBuildDate"]:
        node = channel.find(elem)
        if node is not None:
            node.text = pub_date
        else:
            ET.SubElement(channel, elem).text = pub_date

    # Remove existing items
    for item in channel.findall("item"):
        channel.remove(item)

    print(f"Generating RSS feed with {len(episodes)} episodes")

    for date_str, episode in sorted(episodes.items(), reverse=True):
        print(f"\nProcessing episode from {date_str}")
        item = ET.SubElement(channel, "item")

        # Recreate all original elements with modified title/description
        for elem_data in episode["elements"]:
            tag = elem_data["tag"]
            text = elem_data["text"]
            attrib = elem_data["attrib"]

            # Handle namespaces
            if elem_data["namespace"]:
                full_tag = f"{{{elem_data['namespace']}}}{tag}"
            else:
                full_tag = tag

            # Existing text modification logic
            if tag == "title":
                text = f"{date_str} - {text}"
            elif tag == "description":
                text = f"{date_str} - {text}"
            elif tag == "guid":
                attrib["isPermaLink"] = "false"
            elif (
                tag == "explicit"
                and elem_data["namespace"]
                == "http://www.itunes.com/dtds/podcast-1.0.dtd"
            ):
                text = "false" if text == "no" else text

            element = ET.SubElement(item, full_tag, attrib)
            element.text = text

    ET.indent(root, space="  ", level=0)

    # Generate XML content as string
    xml_content = ET.tostring(
        root, encoding="utf-8", xml_declaration=True, short_empty_elements=False
    )

    # Check against existing content
    try:
        with open(OUTPUT_FEED, "rb") as f:
            existing_content = f.read()
            if existing_content == xml_content:
                print("Feed XML unchanged")
                return False
    except FileNotFoundError:
        pass

    # Write new content if different
    with open(OUTPUT_FEED, "wb") as f:
        f.write(xml_content)
        print("Wrote new feed.xml")

    return True


if __name__ == "__main__":
    episode = get_current_episode()
    if episode:
        if not update_feed(episode):
            print("No updates needed")
