import json

from .types import infer_scalar_type, combine_type

ENUM_MAX_VALUES = 10

_SECRET_NAME_SUBSTRINGS = ("password", "pwd", "secret", "token")


def _looks_like_secret(attr_name):
    lowered = attr_name.lower()
    return any(substring in lowered for substring in _SECRET_NAME_SUBSTRINGS)


class Model:
    def __init__(self):
        self.paths = {}

    def _get_or_create_path(self, path):
        is_new = path not in self.paths
        if is_new:
            self.paths[path] = {
                "attributes": {},
                "children": {},
                "instance_count": 0,
                "order": [],
                "order_stable": True,
                "has_text": False,
            }
        return self.paths[path], is_new

    def merge_element(self, path, attrib, child_tag_counts, has_text):
        events = []
        entry, is_new = self._get_or_create_path(path)
        if is_new:
            events.append({"kind": "new_element", "path": path})

        prev_instance_count = entry["instance_count"]
        new_instance_count = prev_instance_count + 1

        for attr_name, attr_entry in entry["attributes"].items():
            if attr_name in attrib:
                continue
            was_required = attr_entry["attr_seen_count"] == prev_instance_count
            is_required_now = attr_entry["attr_seen_count"] == new_instance_count
            if was_required and not is_required_now:
                events.append({"kind": "now_optional", "path": path, "attr": attr_name})

        entry["instance_count"] = new_instance_count

        for attr_name, value in attrib.items():
            value_type = infer_scalar_type(value)

            if attr_name not in entry["attributes"]:
                if _looks_like_secret(attr_name):
                    entry["attributes"][attr_name] = {
                        "type": value_type,
                        "values": None,
                        "overflowed": True,
                        "attr_seen_count": 1,
                        "labels": {},
                    }
                else:
                    entry["attributes"][attr_name] = {
                        "type": value_type,
                        "values": [value],
                        "overflowed": False,
                        "attr_seen_count": 1,
                        "labels": {},
                    }
                events.append({"kind": "new_attribute", "path": path, "attr": attr_name})
                continue

            attr_entry = entry["attributes"][attr_name]
            attr_entry["type"] = combine_type(attr_entry["type"], value_type)
            attr_entry["attr_seen_count"] += 1

            if attr_entry["overflowed"]:
                continue

            if value in attr_entry["values"]:
                continue

            attr_entry["values"].append(value)
            events.append({"kind": "new_value", "path": path, "attr": attr_name, "value": value})

            if len(attr_entry["values"]) > ENUM_MAX_VALUES:
                attr_entry["overflowed"] = True
                attr_entry["values"] = None
                events.append({"kind": "enum_overflow", "path": path, "attr": attr_name})

        self._merge_children(entry, prev_instance_count, child_tag_counts)

        if has_text:
            entry["has_text"] = True

        return events

    def _merge_children(self, entry, prev_instance_count, child_tag_counts):
        seen_order = list(child_tag_counts.keys())

        for tag, child_entry in entry["children"].items():
            if child_tag_counts.get(tag, 0) == 0:
                child_entry["ever_absent"] = True

        for tag in seen_order:
            count = child_tag_counts[tag]
            if tag not in entry["children"]:
                entry["children"][tag] = {
                    "ever_absent": prev_instance_count > 0,
                    "ever_multiple": count > 1,
                }
                entry["order"].append(tag)
            elif count > 1:
                entry["children"][tag]["ever_multiple"] = True

        common = set(entry["order"]) & set(seen_order)
        order_common = [t for t in entry["order"] if t in common]
        seen_common = [t for t in seen_order if t in common]
        if order_common != seen_common:
            entry["order_stable"] = False

    def to_dict(self):
        return {"paths": self.paths}

    @classmethod
    def from_dict(cls, data):
        model = cls()
        model.paths = data.get("paths", {})
        return model

    def save(self, file_path):
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, sort_keys=True)

    @classmethod
    def load(cls, file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)
