"""Write the 'Add recipe' share-sheet shortcut as a plist, for signing with `shortcuts sign`.

    python3 shortcut/build_import_shortcut.py out.shortcut
    shortcuts sign --mode anyone --input out.shortcut --output "Add recipe.shortcut"

Same actions as SHORTCUT-IMPORT.md. Hand-built plist, no iCloud ids inside.
"""
import plistlib
import sys
import uuid

HOST = "https://recipes.tainik.net:8443"
u = {k: str(uuid.uuid4()).upper() for k in ("link", "page", "text", "post")}


def out(name, key):  # reference another action's output
    return {"Type": "ActionOutput", "OutputName": name, "OutputUUID": u[key]}


def tok(prefix, *refs, suffix=""):  # text with embedded variables: prefix + each ref + suffix
    s, att = prefix, {}
    for r in refs:
        att[f"{{{len(s)}, 1}}"] = r
        s += "￼"
    return {"Value": {"attachmentsByRange": att, "string": s + suffix}, "WFSerializationType": "WFTextTokenString"}


def var(ref):  # a bare variable parameter
    return {"Value": ref, "WFSerializationType": "WFTextTokenAttachment"}


def act(ident, **params):
    return {"WFWorkflowActionIdentifier": ident, "WFWorkflowActionParameters": params}


actions = [
    act("is.workflow.actions.detect.link", UUID=u["link"], CustomOutputName="Page URL",
        WFInput=tok("", {"Type": "ExtensionInput"})),
    act("is.workflow.actions.downloadurl", UUID=u["page"], CustomOutputName="Page HTML",
        WFURL=tok("", out("Page URL", "link")), WFHTTPMethod="GET"),
    act("is.workflow.actions.detect.text", UUID=u["text"], CustomOutputName="HTML text",
        WFInput=tok("", out("Page HTML", "page"))),
    act("is.workflow.actions.downloadurl", UUID=u["post"], CustomOutputName="Result",
        WFURL=tok(HOST + "/api/import"), WFHTTPMethod="POST", WFHTTPBodyType="JSON",
        WFJSONValues={"WFSerializationType": "WFDictionaryFieldValue", "Value": {"WFDictionaryFieldValueItems": [
            {"WFItemType": 0, "WFKey": tok("url"), "WFValue": tok("", out("Page URL", "link"))},
            {"WFItemType": 0, "WFKey": tok("html"), "WFValue": tok("", out("HTML text", "text"))},
        ]}}),
    # ponytail: no If branch; the reply is {"id","name"} or {"error"}, shown as-is
    act("is.workflow.actions.alert", WFAlertActionTitle="Add recipe", WFAlertActionCancelButtonShown=False,
        WFAlertActionMessage=tok("", out("Result", "post"))),
]

shortcut = {
    "WFWorkflowName": "Add recipe",
    "WFWorkflowActions": actions,
    "WFWorkflowClientVersion": "5037.111",
    "WFWorkflowMinimumClientVersion": 1106,
    "WFWorkflowMinimumClientVersionString": "1106",
    "WFWorkflowHasShortcutInputVariables": True,
    "WFWorkflowHasOutputFallback": False,
    "WFWorkflowIcon": {"WFWorkflowIconGlyphNumber": 59511, "WFWorkflowIconStartColor": 4282601983},
    "WFWorkflowImportQuestions": [],
    "WFWorkflowInputContentItemClasses": ["WFURLContentItem", "WFSafariWebPageContentItem"],
    "WFWorkflowNoInputBehavior": {"Name": "WFWorkflowNoInputBehaviorAskForInput", "Parameters": {"ItemClass": "WFURLContentItem"}},
    "WFWorkflowOutputContentItemClasses": [],
    "WFWorkflowTypes": ["ActionExtension", "WFWorkflowTypeShowInSearch"],
    "WFQuickActionSurfaces": [],
}
with open(sys.argv[1], "wb") as f:
    plistlib.dump(shortcut, f)
print(f"wrote {sys.argv[1]}: {len(actions)} actions")
