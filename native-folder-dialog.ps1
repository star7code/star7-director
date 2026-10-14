$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
# Windows Common Item Dialog: the modern Explorer-style folder picker.
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
namespace Star7 {
 [ComImport, Guid("DC1C5A9C-E88A-4DDE-A5A1-60F82A20AEF7")] class FileOpenDialog {}
 [ComImport, Guid("42F85136-DB7E-439C-85F1-E4075D135FC8"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
 interface IFileDialog {
  [PreserveSig] int Show(IntPtr owner);
  void SetFileTypes(uint count, IntPtr specs);
  void SetFileTypeIndex(uint index);
  void GetFileTypeIndex(out uint index);
  void Advise(IntPtr events, out uint cookie);
  void Unadvise(uint cookie);
  void SetOptions(uint options);
  void GetOptions(out uint options);
  void SetDefaultFolder(IShellItem folder);
  void SetFolder(IShellItem folder);
  void GetFolder(out IShellItem folder);
  void GetCurrentSelection(out IShellItem item);
  void SetFileName([MarshalAs(UnmanagedType.LPWStr)] string name);
  void GetFileName(out IntPtr name);
  void SetTitle([MarshalAs(UnmanagedType.LPWStr)] string title);
  void SetOkButtonLabel([MarshalAs(UnmanagedType.LPWStr)] string text);
  void SetFileNameLabel([MarshalAs(UnmanagedType.LPWStr)] string label);
  void GetResult(out IShellItem item);
 }
 [ComImport, Guid("43826D1E-E718-42EE-BC55-A1E261C37BFE"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
 interface IShellItem {
  void BindToHandler(IntPtr context, ref Guid handler, ref Guid iid, out IntPtr result);
  void GetParent(out IShellItem parent);
  void GetDisplayName(uint kind, out IntPtr name);
 }
 public static class FolderPicker {
  [DllImport("user32.dll")] static extern IntPtr GetForegroundWindow();
  public static string Choose() {
   IFileDialog dialog = (IFileDialog)new FileOpenDialog();
   IShellItem item = null; IntPtr name = IntPtr.Zero;
   try {
    uint options; dialog.GetOptions(out options);
    dialog.SetOptions(options | 0x20u | 0x40u | 0x800u | 0x8u | 0x02000000u);
    dialog.SetTitle("选择 Star7 视频保存目录");
    dialog.SetOkButtonLabel("选择此文件夹");
    int result = dialog.Show(GetForegroundWindow());
    if (result == unchecked((int)0x800704C7)) return null;
    Marshal.ThrowExceptionForHR(result);
    dialog.GetResult(out item);
    item.GetDisplayName(0x80058000u, out name);
    return Marshal.PtrToStringUni(name);
   } finally {
    if (name != IntPtr.Zero) Marshal.FreeCoTaskMem(name);
    if (item != null) Marshal.FinalReleaseComObject(item);
    Marshal.FinalReleaseComObject(dialog);
   }
  }
 }
}
'@
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$selected = [Star7.FolderPicker]::Choose()
if ($null -eq $selected) { [Console]::WriteLine('null') }
else { [Console]::WriteLine((ConvertTo-Json -InputObject $selected -Compress)) }
