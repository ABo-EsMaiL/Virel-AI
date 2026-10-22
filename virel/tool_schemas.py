"""Bounded native typed schema projection; original client schemas stay authoritative."""
from dataclasses import dataclass, field
import re
import logging
from .errors import GatewayError

KEYS={"type","properties","required","items","description","enum","additionalProperties",
      "minimum","maximum","exclusiveMinimum","exclusiveMaximum","minLength","maxLength",
      "minItems","maxItems","minProperties","maxProperties","$schema","title","default",
      "anyOf","oneOf","const","$defs","definitions","$ref","examples","example","$comment",
      "deprecated","readOnly","writeOnly","pattern","propertyNames","format"}
TYPES={"object","array","string","number","integer","boolean","null"}
logger = logging.getLogger("virel.webhook")
DIAGNOSTIC_KEYWORDS = {"format", "allOf", "not", "if", "then", "else", "uniqueItems", "multipleOf",
                       "contains", "minContains", "maxContains", "prefixItems", "additionalItems",
                       "patternProperties", "propertyNames", "dependencies", "dependentRequired",
                       "dependentSchemas", "unevaluatedProperties", "unevaluatedItems",
                       "$id", "$anchor", "$dynamicRef", "$dynamicAnchor", "contentEncoding",
                       "contentMediaType", "contentSchema"}

def fail(message, upstream=False):
    raise GatewayError(502 if upstream else 400,message,
                       "invalid_upstream_tool_call" if upstream else "unsupported_capability")

def safe_pattern(pattern):
    """Only single-character atoms with fixed/bounded final repetition; no backtracking groups."""
    if not isinstance(pattern,str) or len(pattern)>256:
        fail("Function pattern must be a bounded safe regular expression.")
    index=1 if pattern.startswith("^") else 0
    end=len(pattern)-1 if pattern.endswith("$") else len(pattern)
    width=0
    while index<end:
        char=pattern[index]
        if char=="[":
            index+=1
            if index<end and pattern[index]=="^": index+=1
            while index<end and pattern[index]!="]":
                index+=2 if pattern[index]=="\\" else 1
            if index>=end: fail("Invalid function pattern.")
            index+=1
        elif char=="\\":
            index+=1
            if index>=end or pattern[index].isdigit() or pattern[index] in "AbBZG":
                fail("Function pattern backreferences and assertions are unavailable.")
            index+=1
        elif char in "().*+?{}|^$":
            fail("Function patterns permit only literal/class atoms and finite repetition.")
        else:
            index+=1
        repeat=1
        if index<end and pattern[index]=="{":
            match=re.match(r"\{(\d{1,3})(?:,(\d{1,3}))?\}",pattern[index:end])
            if not match: fail("Function pattern repetition must have finite bounds.")
            low=int(match[1]); high=int(match[2] or match[1])
            if low>high or high>256: fail("Function pattern repetition exceeds its bound.")
            index+=len(match[0]);repeat=high
            if low!=high and (index!=end or not pattern.startswith("^") or not pattern.endswith("$")):
                fail("A variable pattern repetition must be the final atom of an anchored pattern.")
        width+=repeat
        if width>4096: fail("Function pattern exceeds its expansion bound.")
    try: re.compile(pattern)
    except re.error: fail("Invalid function pattern.")

def value_type(value):
    if value is None: return "null"
    if isinstance(value,bool): return "boolean"
    if isinstance(value,str): return "string"
    if isinstance(value,int): return "integer"
    if isinstance(value,float): return "number"
    if isinstance(value,list): return "array"
    if isinstance(value,dict): return "object"
    fail("Schema literal must be JSON.")

@dataclass
class Projection:
    native: dict
    kind: str
    children: dict=field(default_factory=dict)
    items: object=None
    variants: list=field(default_factory=list)
    additional: object=None
    entry_key: object=None

    @property
    def object_root(self):
        return self.kind=="object" or (bool(self.variants) and all(p.object_root for p in self.variants))

    def decode(self,value):
        if self.variants:
            if not isinstance(value,dict) or len(value)!=1:
                fail("Native union values require exactly one declared variant_N property.",True)
            name,nested=next(iter(value.items()))
            match=re.fullmatch(r"variant_(0|[1-9]\d*)",name)
            if not match or int(match[1])>=len(self.variants):
                fail("Native union variant is unknown.",True)
            return self.variants[int(match[1])].decode(nested)
        if self.kind=="null_signal":
            if value is not True: fail("Native null variant must be true.",True)
            return None
        if isinstance(value,dict):
            if self.entry_key is not None:
                if set(value)-set(self.children)-{self.entry_key}:
                    fail("Native typed maps require their declared map entries transport.",True)
                result={key:self.children[key].decode(item) for key,item in value.items() if key in self.children}
                entries=value.get(self.entry_key,[])
                if not isinstance(entries,list):
                    fail("Native typed map entries must be an array.",True)
                for entry in entries:
                    if not isinstance(entry,dict) or set(entry)!={"key","value"} or not isinstance(entry["key"],str):
                        fail("Native map entries require a string key and typed value.",True)
                    key=entry["key"]
                    if key in result or key in self.children:
                        fail("Native map entries must not duplicate another property.",True)
                    result[key]=self.additional.decode(entry["value"])
                return result
            return {key:self.children[key].decode(item) if key in self.children else item for key,item in value.items()}
        if isinstance(value,list) and self.items:
            return [self.items.decode(item) for item in value]
        return value

def project_schema(schema):
    budget=[4096]
    def target(ref):
        if not isinstance(ref,str) or not ref.startswith("#/"):
            fail("Function refs must be local JSON pointers; remote/file/anchor refs are unavailable.")
        node=schema
        for component in ref[2:].split("/"):
            if re.search(r"~(?![01])",component): fail("Invalid local schema pointer.")
            key=component.replace("~1","/").replace("~0","~")
            if not isinstance(node,dict) or key not in node:
                fail("Local function schema reference was not found.")
            node=node[key]
        if not isinstance(node,dict): fail("Local reference must target a schema object.")
        return node
    def compile(node,depth=0,refs=(),hint=None):
        budget[0]-=1
        if depth>24 or budget[0]<0:
            fail("Native function schema expansion exceeds its bound.")
        if not isinstance(node,dict) or set(node)-KEYS:
            fail("Function schema contains an unsupported keyword; unsafe patterns, structural compositions and dynamic references are unavailable.")
        if "pattern" in node: safe_pattern(node["pattern"])
        if "$ref" in node:
            ref=node["$ref"]
            if ref in refs: fail("Recursive function schema references are unavailable.")
            if set(node)-{"$ref","description","title","default","examples","example","$comment","format"}:
                fail("Local references accept annotation siblings only.")
            result=compile(target(ref),depth+1,refs+(ref,),hint)
            if "description" in node:
                result.native={**result.native,"description":node["description"]}
            return result
        unions=[key for key in ("anyOf","oneOf") if key in node]
        kinds=node.get("type")
        if len(unions)>1: fail("A schema node may contain one union operator.")
        if unions or isinstance(kinds,list):
            if unions:
                if set(node)-{unions[0],"type","description","title","default","examples","example","$comment","$schema","$defs","definitions","format"}:
                    fail("Union structural siblings are unavailable; keep them inside each branch.")
                branches=node[unions[0]]
                if not isinstance(branches,list) or not branches: fail("Schema union requires nonempty branches.")
                choices=[compile(branch,depth+1,refs,kinds if isinstance(kinds,str) else hint) for branch in branches]
            else:
                if not kinds or len(set(kinds))!=len(kinds) or any(kind not in TYPES for kind in kinds):
                    fail("Invalid JSON schema type union.")
                choices=[compile({**node,"type":kind},depth+1,refs) for kind in kinds]
            for index,choice in enumerate(choices):
                if choice.kind=="null":
                    choices[index]=Projection({"type":"boolean","description":"Set true to select JSON null."},"null_signal")
            native={"type":"object","properties":{"variant_"+str(i):choice.native for i,choice in enumerate(choices)},
                    "description":node.get("description","")+" Select exactly one variant_N property; its value is the original typed value."}
            return Projection(native,"union",variants=choices)
        kind=kinds or hint
        if kind is None and "const" in node: kind=value_type(node["const"])
        if kind is None and isinstance(node.get("enum"),list) and node["enum"]:
            enum_kinds=list(dict.fromkeys(value_type(value) for value in node["enum"]))
            return compile({**node,"type":enum_kinds[0] if len(enum_kinds)==1 else enum_kinds},depth+1,refs)
        if not isinstance(kind,str) or kind not in TYPES:
            fail("Every function schema node must have an inferable supported JSON type.")
        native={"type":kind}; children={}; items=None
        # format remains an annotation in the original schema/prompt, as in the Draft validator.
        if "description" in node: native["description"]=node["description"]
        if "enum" in node and kind=="string":
            native["enum"]=[value for value in node["enum"] if isinstance(value,str)]
        if "const" in node and kind=="string": native["enum"]=[node["const"]]
        # JSON Schema applicators affect only their matching instance type.
        if "properties" in node and kind=="object":
            if not isinstance(node["properties"],dict): fail("Invalid schema properties.")
            children={key:compile(value,depth+1,refs) for key,value in node["properties"].items()}
            native["properties"]={key:value.native for key,value in children.items()}
        # The editor removes empty properties, then rejects even an empty required list.
        if kind=="object" and node.get("required"): native["required"]=node["required"]
        if "items" in node and kind=="array":
            items=compile(node["items"],depth+1,refs)
            # AI Studio drops item descriptions on Save; keep their guidance on the array.
            item_description=items.native.pop("description",None)
            if item_description:
                native["description"]=(native.get("description","")+"\nEach item: "+item_description).lstrip("\n")
            native["items"]=items.native
        elif kind=="array": fail("Array schemas require typed items.")
        additional=node.get("additionalProperties",True)
        if not isinstance(additional,(bool,dict)):
            fail("additionalProperties must be boolean or a schema object.")
        value_projection=None; entry_key=None
        if kind=="object" and isinstance(additional,dict) and additional:
            value_projection=compile(additional,depth+1,refs)
            if value_projection.kind=="null":
                value_projection=Projection({"type":"boolean","description":"Set true to select JSON null."},"null_signal")
            entry_key="virel_map_entries"
            index=0
            while entry_key in children:
                index+=1
                entry_key="virel_map_entries_"+str(index)
            native.setdefault("properties",{})[entry_key]={
                "type":"array","description":"Additional properties transport: map entries with unique string keys and typed values. Do not include separately declared properties here.",
                "items":{"type":"object","properties":{"key":{"type":"string"},"value":value_projection.native},
                         "required":["key","value"]}}
            required=node.get("required",[])
            projected_required=[key for key in required if key in children]
            if any(key not in children for key in required):
                projected_required.append(entry_key)
            if projected_required:native["required"]=projected_required
            else:native.pop("required",None)
        return Projection(native,kind,children,items,additional=value_projection,entry_key=entry_key)
    # Inspect unused definition bodies too: no hidden network refs or unsafe regex.
    inspection_budget=[4096]
    def inspect(node,depth=0,refs=()):
        inspection_budget[0]-=1
        if depth>24 or inspection_budget[0]<0: fail("Function schema exceeds its nesting bound.")
        if not isinstance(node,dict) or set(node)-KEYS:
            unknown = set(node)-KEYS if isinstance(node,dict) else set()
            labels = sorted(key if key in DIAGNOSTIC_KEYWORDS else "<unknown>" for key in unknown)[:16]
            logger.warning("Function schema rejected depth=%d node_type=%s unsupported=%s count=%d",
                           depth, type(node).__name__, labels, len(unknown))
            fail("Unsupported function schema keyword.")
        if "pattern" in node: safe_pattern(node["pattern"])
        if "$ref" in node:
            ref=node["$ref"]
            if ref in refs: fail("Recursive function schema references are unavailable.")
            inspect(target(ref),depth+1,refs+(ref,))
        for key in ("properties","$defs","definitions"):
            if key in node:
                if not isinstance(node[key],dict): fail("Invalid schema map.")
                for child in node[key].values(): inspect(child,depth+1,refs)
        # Key constraints stay in the original validator; the native editor has no equivalent field.
        if "propertyNames" in node and type(node["propertyNames"]) is not bool:
            inspect(node["propertyNames"],depth+1,refs)
        additional=node.get("additionalProperties")
        if isinstance(additional,dict) and additional:
            inspect(additional,depth+1,refs)
        if "items" in node: inspect(node["items"],depth+1,refs)
        for key in ("anyOf","oneOf"):
            if key in node:
                if not isinstance(node[key],list): fail("Invalid union branches.")
                for child in node[key]: inspect(child,depth+1,refs)
    inspect(schema)
    return compile(schema)
