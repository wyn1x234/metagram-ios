#!/usr/bin/env python3
import pathlib
import re
import sys


def replace_body(text, signature, interior):
    marker = interior.strip()
    start = text.find(signature)
    if start < 0:
        if marker in text:
            return text, "already"
        raise SystemExit("missing signature: " + signature.split("(")[0].strip())
    brace = text.find("{", start)
    if brace < 0:
        raise SystemExit("missing brace: " + signature.split("(")[0].strip())
    depth = 0
    end = None
    for index in range(brace, len(text)):
        char = text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                end = index
                break
    if end is None:
        raise SystemExit("unbalanced brace: " + signature.split("(")[0].strip())
    current = text[brace + 1:end]
    if current.strip() == marker:
        return text, "already"
    return text[: brace + 1] + "\n" + interior + "\n" + text[end:], "patched"


def replace_text(text, old, new, label):
    if old not in text:
        if new in text:
            return text, "already"
        raise SystemExit("missing anchor: " + label)
    return text.replace(old, new, 1), "patched"


def write(path, text):
    path.write_text(text, encoding="utf-8", newline="\n")


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: apply_metagram.py Telegram-iOS")
    root = pathlib.Path(sys.argv[1])
    if not (root / "build-system" / "Make" / "Make.py").is_file():
        raise SystemExit("this is not a Telegram-iOS checkout: " + str(root))

    presence = root / "submodules/TelegramCore/Sources/State/ManagedAccountPresence.swift"
    text = presence.read_text(encoding="utf-8")
    text, status = replace_body(
        text,
        "private func updatePresence(_ isOnline: Bool)",
        """        self.onlineTimer?.invalidate()
        self.onlineTimer = nil
        let request: Signal<Api.Bool, MTRpcError> = self.network.request(Api.functions.account.updateStatus(offline: .boolTrue))
        self.isPerformingUpdate.set(true)
        self.currentRequestDisposable.set((request
        |> `catch` { _ -> Signal<Api.Bool, NoError> in
            return .single(.boolFalse)
        }
        |> deliverOn(self.queue)).start(completed: { [weak self] in
            guard let strongSelf = self else {
                return
            }
            strongSelf.isPerformingUpdate.set(false)
        }))""",
    )
    write(presence, text)
    print("presence", status)

    reads = root / "submodules/TelegramCore/Sources/State/SynchronizePeerReadState.swift"
    text = reads.read_text(encoding="utf-8")
    text, status = replace_body(
        text,
        "private func pushPeerReadState(network: Network, postbox: Postbox, stateManager: AccountStateManager, peerId: PeerId, readState: PeerReadState)",
        "    return .single(readState)",
    )
    write(reads, text)
    print("read-receipts", status)

    typing = root / "submodules/TelegramCore/Sources/State/ManagedLocalInputActivities.swift"
    text = typing.read_text(encoding="utf-8")
    text, status = replace_body(
        text,
        "private func requestActivity(postbox: Postbox, network: Network, accountPeerId: PeerId, peerId: PeerId, threadId: Int64?, activity: PeerInputActivity?)",
        "    return .complete()",
    )
    write(typing, text)
    print("typing", status)

    stories = root / "submodules/TelegramCore/Sources/State/ManagedSynchronizeViewStoriesOperations.swift"
    text = stories.read_text(encoding="utf-8")
    text, status = replace_body(
        text,
        "private func pushStoriesAreSeen(postbox: Postbox, network: Network, stateManager: AccountStateManager, peer: Peer, operation: SynchronizeViewStoriesOperation)",
        "    return .complete()",
    )
    write(stories, text)
    print("stories-read", status)

    story_engine = root / "submodules/TelegramCore/Sources/TelegramEngine/Messages/Stories.swift"
    text = story_engine.read_text(encoding="utf-8")
    old = """            return account.network.request(Api.functions.stories.incrementStoryViews(peer: inputPeer, id: [id]))
            |> `catch` { _ -> Signal<Api.Bool, NoError> in
                return .single(.boolFalse)
            }
            |> ignoreValues"""
    new = "            return .complete()"
    text, status = replace_text(text, old, new, "story views")
    write(story_engine, text)
    print("story-views", status)

    attribute = root / "submodules/TelegramCore/Sources/SyncCore/MetaGramDeletedMessageAttribute.swift"
    attribute_text = """import Foundation
import Postbox

public final class MetaGramDeletedMessageAttribute: MessageAttribute {
    public init() {
    }

    public required init(decoder: PostboxDecoder) {
        let _ = decoder.decodeInt32ForKey("m", orElse: 1)
    }

    public func encode(_ encoder: PostboxEncoder) {
        encoder.encodeInt32(1, forKey: "m")
    }
}

public func markMessagesKeptAfterRemoteDelete(transaction: Transaction, ids: [MessageId]) {
    for id in ids {
        transaction.updateMessage(id, update: { message in
            if message.attributes.contains(where: { $0 is MetaGramDeletedMessageAttribute }) {
                return .skip
            }
            var attributes = message.attributes
            attributes.append(MetaGramDeletedMessageAttribute())
            var storeForwardInfo: StoreMessageForwardInfo?
            if let forwardInfo = message.forwardInfo {
                storeForwardInfo = StoreMessageForwardInfo(authorId: forwardInfo.author?.id, sourceId: forwardInfo.source?.id, sourceMessageId: forwardInfo.sourceMessageId, date: forwardInfo.date, authorSignature: forwardInfo.authorSignature, psaType: forwardInfo.psaType, flags: forwardInfo.flags)
            }
            return .update(StoreMessage(id: message.id, customStableId: nil, globallyUniqueId: message.globallyUniqueId, groupingKey: message.groupingKey, threadId: message.threadId, timestamp: message.timestamp, flags: StoreMessageFlags(message.flags), tags: message.tags, globalTags: message.globalTags, localTags: message.localTags, forwardInfo: storeForwardInfo, authorId: message.author?.id, text: message.text, attributes: attributes, media: message.media))
        })
    }
}
"""
    if attribute.is_file() and "MetaGramDeletedMessageAttribute" in attribute.read_text(encoding="utf-8"):
        print("deleted-attribute", "already")
    else:
        attribute.parent.mkdir(parents=True, exist_ok=True)
        write(attribute, attribute_text)
        print("deleted-attribute", "patched")

    account = root / "submodules/TelegramCore/Sources/Account/AccountManager.swift"
    text = account.read_text(encoding="utf-8")
    registration = "    declareEncodable(MetaGramDeletedMessageAttribute.self, f: { MetaGramDeletedMessageAttribute(decoder: $0) })\n"
    anchor = "    declareEncodable(EditedMessageAttribute.self, f: { EditedMessageAttribute(decoder: $0) })\n"
    if registration in text:
        print("attribute-registration", "already")
    else:
        text, status = replace_text(text, anchor, anchor + registration, "attribute registration")
        write(account, text)
        print("attribute-registration", status)

    replay = root / "submodules/TelegramCore/Sources/State/Sync/StateReplay+Messages.swift"
    text = replay.read_text(encoding="utf-8")
    text, status = replace_body(
        text,
        "func applyDeleteMessagesWithGlobalIds(_ ids: [Int32])",
        "        markMessagesKeptAfterRemoteDelete(transaction: transaction, ids: transaction.messageIdsForGlobalIds(ids))",
    )
    text, channel_status = replace_body(
        text,
        "func applyDeleteMessages(_ ids: [MessageId])",
        "        markMessagesKeptAfterRemoteDelete(transaction: transaction, ids: ids)",
    )
    write(replay, text)
    print("keep-deleted", status, channel_status)

    timestamp = root / "submodules/TelegramUI/Components/Chat/ChatMessageDateAndStatusNode/Sources/StringForMessageTimestampStatus.swift"
    text = timestamp.read_text(encoding="utf-8")
    old = """    if case .minimal = format {
        
    } else {
        if let authorTitle = authorTitle, !authorTitle.isEmpty {
            dateText = "\\(authorTitle), \\(dateText)"
        }
    }
    
    return dateText
"""
    new = """    if case .minimal = format {
        
    } else {
        if let authorTitle = authorTitle, !authorTitle.isEmpty {
            dateText = "\\(authorTitle), \\(dateText)"
        }
    }

    if message.attributes.contains(where: { $0 is MetaGramDeletedMessageAttribute }) {
        dateText = "◆ \\(dateText)"
    }
    return dateText
"""
    text, status = replace_text(text, old, new, "deleted mark")
    write(timestamp, text)
    print("deleted-mark", status)

    settings = root / "submodules/TelegramUIPreferences/Sources/ExperimentalUISettings.swift"
    text = settings.read_text(encoding="utf-8")
    old = """            keepChatNavigationStack: false,
            skipReadHistory: false,"""
    new = """            keepChatNavigationStack: false,
            skipReadHistory: true,"""
    text, status = replace_text(text, old, new, "skip read history")
    write(settings, text)
    print("skip-read-history", status)

    renamed = 0
    app = root / "Telegram" / "Telegram-iOS"
    for strings in app.rglob("InfoPlist.strings"):
        original = strings.read_text(encoding="utf-8")
        updated = re.sub(
            r'("CFBundleDisplayName"\s*=\s*")[^"]*(")',
            r"\1MetaGram\2",
            original,
        )
        if updated != original:
            write(strings, updated)
            renamed += 1
    print("display-name", renamed)


if __name__ == "__main__":
    main()
