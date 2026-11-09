# Installing Urdu Translator on an offline Windows 10 computer

This computer does not need an internet connection. Do not connect it to install, start, or use Urdu Translator.

The installer does not contain the translation model. The model is a separate file, about 4.9 GB, named:

`gemma-4-E4B_q4_0-it.gguf`

## 1. Install the application

1. Copy `UrduTranslator-Setup-1.0.0-x64.exe` to this computer on a USB drive.
2. Run the installer.
3. Accept the folder it offers under Program Files, or choose another folder on this computer.
4. Leave "Create a desktop shortcut" ticked only if you want a desktop icon.
5. Finish the installation. Windows will not be asked to download Python, a runtime, or a model.

The Start menu will contain **Urdu Translator**.

## 2. Copy the model on a different computer

On a computer that is allowed to use the internet:

1. Obtain the Gemma 4 E4B Q4_0 GGUF file named `gemma-4-E4B_q4_0-it.gguf`.
2. Copy that file onto a USB drive. Do not rename it unless you still keep the `.gguf` ending. The setup screen shows the expected file name.
3. Eject the USB drive.

## 3. Bring the model to this computer

1. Plug the USB drive into this offline computer.
2. Start **Urdu Translator**.
3. The window **Gemma AI Model Setup** opens because the model is not on this computer yet.
4. Click **Browse for Model** and select `gemma-4-E4B_q4_0-it.gguf` on the USB drive. A folder on this computer is also fine if you already copied the file there.
5. Choose one of the two options:
   - **Keep model at its current location** if the USB drive will stay connected while you translate.
   - **Copy model to the recommended local model directory** if you want a copy on this computer. The copy is placed in `%LOCALAPPDATA%\UrduTranslator\Models\`. The file on the USB drive is not deleted or changed. Copying 4.9 GB takes a while. The progress bar shows how far the copy has got.
6. Click **Verify Model**. The application checks that the file can be read and asks the local translation program to open it. Nothing is downloaded.
7. When the status says **AI Model Ready — Offline Mode**, you can translate.

The next time you start the application it remembers that file. It asks again only if the file is missing, for example when the USB drive is unplugged and you had chosen to keep the model there. Reconnect the drive, or browse to another copy. The application will not fetch a model from the internet.

## 4. Translate

1. Type or open Urdu text in the left panel.
2. Click **Translate**.
3. English appears on the right. The summary tools are under the English text.
4. History, text files, and Word files are saved on this computer.

Translation and summaries talk only to a program on this same computer (`127.0.0.1`). They do not use a website.

## If something goes wrong

- **Gemma AI Model Setup says the file is unavailable.** The USB drive is unplugged or the file was moved. Reconnect it, or click Browse for Model and choose the file again.
- **The file is empty or is not a GGUF file.** Copy the model file again from the computer where you first saved it. Do not use a shortcut or a part-downloaded file.
- **llama-server cannot start.** The installer is incomplete. Use a copy of the installer that was built with `llama-server.exe` and its DLL files. Do not try to download those files on this computer.
- **Port 8080 is already in use.** Another program is using that port. Urdu Translator leaves that program running and tells you. Close the other program, then try Verify Model or Translate again.
- **Uninstall.** Removing Urdu Translator deletes the Program Files copy only. Your history and a model you copied into `%LOCALAPPDATA%\UrduTranslator\` stay on the computer. Delete that folder yourself only if you want those files gone.
