#!/usr/bin/env swift
import Foundation
import UserNotifications

private let categoryIdentifier = "com.pelagos.confirm";
private let executeIdentifier = "com.pelagos.confirm.execute";
private let skipIdentifier = "com.pelagos.confirm.skip";

final class PelagosDelegate: NSObject, UNUserNotificationCenterDelegate {
    private let handler: (String) -> Void

    init(handler: @escaping (String) -> Void) {
        self.handler = handler
    }

    func userNotificationCenter(_ center: UNUserNotificationCenter, didReceive response: UNNotificationResponse, withCompletionHandler completionHandler: @escaping () -> Void) {
        defer { completionHandler() }

        switch response.actionIdentifier {
        case executeIdentifier, UNNotificationDefaultActionIdentifier:
            handler("EXECUTE")
        case skipIdentifier, UNNotificationDismissActionIdentifier:
            handler("SKIP")
        default:
            handler("SKIP")
        }
    }

    func userNotificationCenter(_ center: UNUserNotificationCenter, willPresent notification: UNNotification, withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void) {
        completionHandler([.banner, .sound])
    }
}

let args = CommandLine.arguments
guard args.count >= 7 else {
    fputs("Usage: \(args[0]) <title> <subtitle> <message> <actionTitle> <otherTitle> <timeout>\n", stderr)
    exit(2)
}

let title = args[1]
let subtitle = args[2]
let message = args[3]
let actionTitle = args[4]
let otherTitle = args[5]
let timeoutSeconds = Double(args[6]) ?? 120.0

if Bundle.main.bundleIdentifier == nil {
    Bundle.main.setValue("com.pelagos.notify", forKey: "bundleIdentifier")
}

let center = UNUserNotificationCenter.current()

var authorizationGranted = false
var authorizationError: Error?
let authSemaphore = DispatchSemaphore(value: 0)

center.requestAuthorization(options: [.alert, .sound]) { granted, error in
    authorizationGranted = granted
    authorizationError = error
    authSemaphore.signal()
}

if authSemaphore.wait(timeout: .now() + 5) == .timedOut {
    fputs("Notification authorization request timed out.\n", stderr)
    exit(1)
}

if let error = authorizationError {
    fputs("Notification authorization failed: \(error)\n", stderr)
    exit(1)
}

if !authorizationGranted {
    fputs("Notification authorization denied.\n", stderr)
    exit(1)
}

let executeAction = UNNotificationAction(identifier: executeIdentifier, title: actionTitle, options: [.foreground])
let skipAction = UNNotificationAction(identifier: skipIdentifier, title: otherTitle, options: [])
let category = UNNotificationCategory(identifier: categoryIdentifier, actions: [executeAction, skipAction], intentIdentifiers: [], options: [])
center.setNotificationCategories([category])

var selection = "TIMEOUT"
let delegate = PelagosDelegate { chosen in
    selection = chosen
}
center.delegate = delegate

let content = UNMutableNotificationContent()
content.title = title
if !subtitle.isEmpty {
    content.subtitle = subtitle
}
if !message.isEmpty {
    content.body = message
}
content.categoryIdentifier = categoryIdentifier
content.sound = UNNotificationSound.default

let identifier = UUID().uuidString
let trigger = UNTimeIntervalNotificationTrigger(timeInterval: 0.2, repeats: false)
let request = UNNotificationRequest(identifier: identifier, content: content, trigger: trigger)

var addError: Error?
let addSemaphore = DispatchSemaphore(value: 0)
center.add(request) { error in
    addError = error
    addSemaphore.signal()
}

if addSemaphore.wait(timeout: .now() + 5) == .timedOut {
    fputs("Scheduling notification timed out.\n", stderr)
    exit(1)
}

if let error = addError {
    fputs("Failed to schedule notification: \(error)\n", stderr)
    exit(1)
}

let timeoutDate = Date().addingTimeInterval(timeoutSeconds)
let runLoop = RunLoop.current

while selection == "TIMEOUT" && Date() < timeoutDate {
    runLoop.run(mode: .default, before: Date(timeIntervalSinceNow: 0.2))
}

center.removePendingNotificationRequests(withIdentifiers: [identifier])
center.removeDeliveredNotifications(withIdentifiers: [identifier])
center.delegate = nil

if selection == "TIMEOUT" && Date() >= timeoutDate {
    print("TIMEOUT")
} else {
    print(selection)
}
