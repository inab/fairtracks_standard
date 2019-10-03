import argparse
import os
from collections import OrderedDict

import json
import xml.etree.ElementTree as ElementTree


ATTRIBS_TO_IMPORT = ['description', 'unique', 'autogenerated', 'enum', 'pattern', 'const', 'ref', 'type',
                     'format', 'ontology', 'namespace', 'matchType', 'foreignProperty', 'minItems']
ATTRIB_CONVERT_MAPPINGS = {'ref': '$ref'}
INTEGER_ATTRIBS = ['minItems']
ALWAYS_ARRAY_ATTRIBS = ['examples']
NEVER_ARRAY_ATTRIBS = ['pattern']
ARRAY_SPLIT_TEXT = '|'
MAX_EXAMPLES_COUNT = 4
BOOLEAN_MAP = {'true': True, 'false': False}


# Public methods

def main():
    parser = argparse.ArgumentParser(description='Generate JSON schema or example '
                                                 'JSON from OPML overview file')
    parser.add_argument('json_type', choices=['schema', 'example'])
    parser.add_argument('in_opml', type=argparse.FileType('r'))
    parser.add_argument('out_json', type=argparse.FileType('w'))
    args = parser.parse_args()

    if args.json_type == 'schema':
        json_dict = create_json_schema_dict(args.in_opml.name)
    else:  # example
        json_dict = create_json_example_dict(args.in_opml.name)

    args.out_json.write(json.dumps(json_dict, indent=4))


def create_json_schema_dict(ompl_path):
    opml_root = ElementTree.parse(ompl_path).find('./body')

    json_schema_dict = _json_schema_create_root(opml_root)
    _json_schema_create_subtree(opml_root, json_parent=json_schema_dict)
    json_schema_dict = _json_schema_add_end_root_attribs(json_schema_dict)

    return json_schema_dict


def create_json_example_dict(ompl_path, example_index=None):
    opml_root = ElementTree.parse(ompl_path).find('./body')

    json_example_dict = OrderedDict()
    _json_example_create_subtree(ompl_path, opml_root,
                                json_parent=json_example_dict,
                                example_index=example_index)

    return json_example_dict


# JSON schema internal methods

def _json_schema_create_root(opml_root):
    json_dict = OrderedDict()
    json_dict['$schema'] = "http://json-schema.org/draft-07/schema#"
    json_dict['$id'] = opml_root.find(".//outline[@text='@schema']").attrib['const']
    json_dict['title'] = opml_root.find(".//outline[@text='#title']").attrib['const']
    json_dict['type'] = 'object'
    return json_dict


def _json_schema_create_subtree(opml_root, json_parent):
    for opml_elem in opml_root:
        json_child = _json_schema_create_child(opml_elem)
        _json_schema_create_subtree(opml_root=opml_elem, json_parent=json_child)
        _json_schema_add_child_to_parent(opml_elem, json_child, json_parent)


def _json_schema_create_child(opml_elem):
    json_child = OrderedDict()

    for attrib in ATTRIBS_TO_IMPORT:
        _json_schema_add_attrib_to_child(opml_elem, json_child, attrib)

    if 'type' in opml_elem.attrib and opml_elem.attrib['type'] == 'array':
        json_child['items'] = OrderedDict()

    return json_child


def _json_schema_add_attrib_to_child(opml_elem, json_child, attrib_name):
    if attrib_name in opml_elem.attrib:
        element_value = opml_elem.attrib[attrib_name]
        if attrib_name in ATTRIB_CONVERT_MAPPINGS:
            attrib_name = ATTRIB_CONVERT_MAPPINGS[attrib_name]
        if element_value:
            if element_value in BOOLEAN_MAP.keys():
                json_child[attrib_name] = BOOLEAN_MAP[element_value]
            elif attrib_name in ALWAYS_ARRAY_ATTRIBS or (( attrib_name not in NEVER_ARRAY_ATTRIBS ) and ( ARRAY_SPLIT_TEXT in element_value )):
                json_child[attrib_name] = [_ for _ in element_value.split(ARRAY_SPLIT_TEXT)]
            elif attrib_name in INTEGER_ATTRIBS:
                json_child[attrib_name] = int(element_value)
            else:
                json_child[attrib_name] = element_value


def _json_schema_add_child_to_parent(element, json_child, json_parent):
    if 'items' in json_parent:
        json_parent['items'] = json_child
    else:
        if 'properties' not in json_parent:
            json_parent['properties'] = OrderedDict()

        key = element.attrib['text']
        if key.startswith('#'):
            return

        json_parent['properties'][key] = json_child

        if element.attrib['required'] == 'true':
            if 'required' not in json_parent:
                json_parent['required'] = []
            json_parent['required'].append(key)

        if 'anyOf' in element.attrib and element.attrib['anyOf'] == 'true':
            if 'anyOf' not in json_parent:
                json_parent['anyOf'] = []
            json_parent['anyOf'].append({'required': [key]})


def _json_schema_add_end_root_attribs(json_dict):
    json_dict['additionalProperties'] = True
    # json_dict['primary_key'] = []
    return json_dict


# JSON example internal methods

def _json_example_create_subtree(opml_path, opml_root, json_parent, example_index):
    for opml_elem in opml_root:
        if _is_ref(opml_elem):
            json_child = _json_example_get_child_for_ref(opml_path, opml_elem, example_index)
            _json_example_add_child_to_parent(opml_elem, json_child, json_parent)
        else:
            json_elem_array = _json_example_convert_opml_elem_to_json_array(opml_elem)

            if json_elem_array:
                json_child = _json_example_get_child_recursively(opml_path, opml_elem,
                                                                 json_elem_array, example_index)
                _json_example_add_child_to_parent(opml_elem, json_child, json_parent)


def _json_example_get_child_for_ref(opml_path, opml_elem, example_index):
    ref_opml_path = _generate_opml_path_from_ref(opml_path, opml_elem)
    json_child = create_json_example_dict(ref_opml_path, example_index=example_index)
    if "@schema" in json_child:
        del json_child['@schema']
    return json_child


def _json_example_add_child_to_parent(element, json_child, json_parent):
    if isinstance(json_parent, dict):
        key = element.attrib['text']
        if key.startswith('#'):
            return
        json_parent[key] = json_child
    else:  # array
        json_parent.append(json_child)


def _json_example_convert_opml_elem_to_json_array(opml_elem):
    el_type = opml_elem.attrib['type']

    if el_type == 'object':
        return [OrderedDict()]
    elif el_type == 'array':
        return [[]]
    else:
        el_examples = opml_elem.attrib.get('examples')
        el_const = opml_elem.attrib.get('const')

        if el_examples:
            return el_examples.split(ARRAY_SPLIT_TEXT)
        elif el_const:
            return [el_const] * MAX_EXAMPLES_COUNT
        else:
            return []


def _json_example_get_child_recursively(opml_path, opml_elem, json_elem_array, example_index):
    if _is_example_content(json_elem_array) and _tree_has_been_split_into_arrays(example_index):
        json_child = json_elem_array[example_index]
    else:
        json_child = json_elem_array[0]

    if _is_array(json_child) and not _tree_has_been_split_into_arrays(example_index):
        child_example_indices = range(MAX_EXAMPLES_COUNT)
    else:
        child_example_indices = [example_index]

    for child_example_index in child_example_indices:
        try:
            _json_example_create_subtree(opml_path,
                                         opml_root=opml_elem,
                                         json_parent=json_child,
                                         example_index=child_example_index)
        except IndexError:
            pass

    return json_child


# JSON example helper methods

def _is_ref(opml_elem):
    return 'ref' in opml_elem.attrib


def _generate_opml_path_from_ref(opml_path, opml_elem):
    return os.path.join(
        os.path.dirname(opml_path),
        os.path.basename(_get_ref(opml_elem)).replace('.schema.json', '.overview.opml')
    )


def _get_ref(opml_elem):
    return opml_elem.attrib['ref']


def _is_example_content(json_elem_array):
    return not any(isinstance(json_elem_array[0], _) for _ in [list, dict])


def _tree_has_been_split_into_arrays(example_index):
    return example_index is not None


def _is_array(json_child):
    return isinstance(json_child, list)


if __name__ == "__main__":
    main()
