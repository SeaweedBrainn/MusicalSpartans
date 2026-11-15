// Optional on-device OCR helper. Build on macOS:
// swiftc AppleOCR.swift -O -o apple-ocr
import Foundation
import Vision

func fail(_ message: String) -> Never {
    FileHandle.standardError.write(Data((message + "\n").utf8))
    exit(1)
}
guard CommandLine.arguments.count == 2 else { fail("Usage: apple-ocr image.png") }
if #available(macOS 10.15, *) {
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.recognitionLanguages = ["en-US"]
    request.usesLanguageCorrection = false
    request.minimumTextHeight = 0.003
    do {
        let handler = VNImageRequestHandler(url: URL(fileURLWithPath: CommandLine.arguments[1]), options: [:])
        try handler.perform([request])
        let observations = request.results ?? []
        let items: [[String: Any]] = observations.compactMap { observation in
            guard let candidate = observation.topCandidates(1).first else { return nil }
            let box = observation.boundingBox
            return ["text": candidate.string, "confidence": Double(candidate.confidence)*100,
                    "left": Double(box.minX), "top": Double(1-box.maxY),
                    "width": Double(box.width), "height": Double(box.height)]
        }
        let data = try JSONSerialization.data(withJSONObject: items, options: [.sortedKeys])
        FileHandle.standardOutput.write(data)
    } catch { fail("Apple Vision OCR failed: \(error)") }
} else { fail("Apple Vision text recognition requires macOS 10.15 or newer.") }
