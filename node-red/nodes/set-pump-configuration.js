import { setPumpConfiguration } from "../../lib/scope.js"

export default function (RED) {
  function Node(config) {
    RED.nodes.createNode(this, config)
    const node = this
    node.on("input", function (msg, send, done) {
      const { configuration } = msg.payload
      setPumpConfiguration(configuration)
        .then(() => {
          send(msg)
          done()
        })
        .catch(done)
    })
  }

  RED.nodes.registerType("set pump configuration", Node)
}
