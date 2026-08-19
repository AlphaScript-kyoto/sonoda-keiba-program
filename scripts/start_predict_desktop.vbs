Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
root = fso.GetParentFolderName(fso.GetParentFolderName(WScript.ScriptFullName))
pythonw = root & "\.venv\Scripts\pythonw.exe"
script = root & "\app\predict_desktop.py"
If Not fso.FileExists(pythonw) Then
  MsgBox "pythonw.exe not found:" & vbCrLf & pythonw, 16, "Sonoda Predict"
  WScript.Quit 1
End If
sh.CurrentDirectory = root
' 0 = hidden window, False = do not wait
sh.Run """" & pythonw & """ """ & script & """", 0, False