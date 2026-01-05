; AutoHotkey script to automate WhatsApp Desktop call button click

; Set the window match mode to find windows by partial title
SetTitleMatchMode, 2

; Wait for the WhatsApp Desktop window to appear (title includes "WhatsApp")
WinWait, WhatsApp

; Activate the WhatsApp window
WinActivate, WhatsApp

; Add a small delay to ensure the window is fully active
Sleep, 1000

Click, 348, 123
Sleep, 500

; Click at position 156, 124 (first button/field)
Click, 156, 124

; Wait for the interface to respond
Sleep, 500

; Type "Zam"
Send, Zam

; Wait after typing
Sleep, 500

; Click at position 171, 349 (second button)
Click, 171, 349

; Wait for action to complete
Sleep, 500

; Click at position 821, 73 (call button)
Click, 821, 73

; Wait for call to initiate
Sleep, 500

