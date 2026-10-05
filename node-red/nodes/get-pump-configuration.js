import { getPumpConfiguration } from "../../lib/scope.js"

export default function (RED) {
  function Node(config) {
    RED.nodes.createNode(this, config)
    const node = this
    node.on("input", function (msg, send, done) {
      getPumpConfiguration()
        .then((configuration) => {
          msg.payload ??= {}
          Object.assign(msg.payload, { configuration })
          send(msg)
          done()
        })
        .catch(done)
    })
  }

  RED.nodes.registerType("get pump configuration", Node)
}
